import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";
import ts from "typescript";
import postcss from "postcss";
import {
  preserveOperationAcceptance,
  preserveComponentAcceptance,
} from "./workbuddy-inventory.mjs";

const dashboard = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const src = path.join(dashboard, "src");
const docs = path.join(dashboard, "../docs/workbuddy-migration");
const manifest = JSON.parse(
  fs.readFileSync(path.join(docs, "source-manifest.json"), "utf8"),
);
const hash = (data) => crypto.createHash("sha256").update(data).digest("hex");
for (const filename of manifest.copied) {
  const expected = manifest.assets.find((asset) => asset.file === filename);
  const content = fs.readFileSync(
    path.join(dashboard, "public/workbuddy", filename),
  );
  if (!expected || hash(content) !== expected.sha256)
    throw new Error(`Copied source resource drift: ${filename}`);
}
for (const asset of manifest.generated) {
  const content = fs.readFileSync(
    path.join(src, "workbuddy/generated", asset.file),
  );
  if (hash(content) !== asset.sha256)
    throw new Error(
      `Generated asset drift: ${asset.file}; run workbuddy:extract`,
    );
  if (!asset.file.endsWith(".css")) continue;
  postcss.parse(content).walkRules((rule) => {
    if (rule.parent.type === "atrule" && /keyframes$/.test(rule.parent.name))
      return;
    for (const selector of postcss.list.comma(rule.selector)) {
      if (!selector.startsWith(':where(html[data-ui="workbuddy"]'))
        throw new Error(`Unscoped selector: ${selector}`);
    }
  });
}

const apiDir = path.join(src, "api/modules");
const apiFiles = fs
  .readdirSync(apiDir)
  .filter((name) => name.endsWith(".ts") && !name.includes(".test."));
const operations = [];
for (const filename of apiFiles) {
  const apiContent = fs.readFileSync(path.join(apiDir, filename), "utf8");
  const apiSha256 = hash(apiContent);
  const source = ts.createSourceFile(
    filename,
    apiContent,
    ts.ScriptTarget.Latest,
    true,
  );
  for (const statement of source.statements) {
    if (
      !statement.modifiers?.some((m) => m.kind === ts.SyntaxKind.ExportKeyword)
    )
      continue;
    if (ts.isFunctionDeclaration(statement) && statement.name) {
      operations.push({
        module: filename,
        apiSha256,
        symbol: statement.name.text,
        operation: statement.name.text,
        line:
          source.getLineAndCharacterOfPosition(statement.getStart()).line + 1,
        consumers: [],
        verification: "pending",
      });
    }
    if (!ts.isVariableStatement(statement)) continue;
    for (const declaration of statement.declarationList.declarations) {
      if (
        !ts.isIdentifier(declaration.name) ||
        !declaration.initializer ||
        !ts.isObjectLiteralExpression(declaration.initializer)
      )
        continue;
      for (const member of declaration.initializer.properties) {
        if (
          !member.name ||
          (!ts.isMethodDeclaration(member) &&
            !(
              ts.isPropertyAssignment(member) &&
              (ts.isArrowFunction(member.initializer) ||
                ts.isFunctionExpression(member.initializer))
            ))
        )
          continue;
        operations.push({
          module: filename,
          apiSha256,
          symbol: declaration.name.text,
          operation: member.name.getText(source).replace(/["']/g, ""),
          line:
            source.getLineAndCharacterOfPosition(member.getStart()).line + 1,
          consumers: [],
          verification: "pending",
        });
      }
    }
  }
}
const operationIndex = new Map(
  operations.map((op) => [`${op.symbol}.${op.operation}`, op]),
);
function walkFiles(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const filename = path.join(dir, entry.name);
    return entry.isDirectory() ? walkFiles(filename) : [filename];
  });
}
for (const filename of walkFiles(src)) {
  if (
    !/\.tsx?$/.test(filename) ||
    filename.includes(".test.") ||
    filename.startsWith(apiDir)
  )
    continue;
  const source = ts.createSourceFile(
    filename,
    fs.readFileSync(filename, "utf8"),
    ts.ScriptTarget.Latest,
    true,
  );
  const aliases = new Map();
  for (const statement of source.statements) {
    if (!ts.isImportDeclaration(statement)) continue;
    const bindings = statement.importClause?.namedBindings;
    if (!bindings || !ts.isNamedImports(bindings)) continue;
    for (const item of bindings.elements)
      aliases.set(item.name.text, item.propertyName?.text ?? item.name.text);
  }
  const visit = (node) => {
    if (ts.isCallExpression(node)) {
      const callee = node.expression;
      let key;
      if (
        ts.isPropertyAccessExpression(callee) &&
        ts.isIdentifier(callee.expression)
      ) {
        key = `${
          aliases.get(callee.expression.text) ?? callee.expression.text
        }.${callee.name.text}`;
      } else if (ts.isIdentifier(callee)) {
        const name = aliases.get(callee.text) ?? callee.text;
        key = `${name}.${name}`;
      }
      const operation = operationIndex.get(key);
      if (operation)
        operation.consumers.push({
          file: path.relative(dashboard, filename),
          line: source.getLineAndCharacterOfPosition(node.getStart()).line + 1,
        });
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
}
const components = [
  ...new Map(
    manifest.modules
      .filter((m) => /\.(tsx|vue)$/.test(m.original))
      .map((m) => [m.original, m]),
  ).values(),
].map((item) => ({
  ...item,
  sourceFingerprint: manifest.sourceFingerprint,
  kind: /modal|dialog|drawer|popup/i.test(item.original)
    ? "overlay"
    : /pages\/|views\//.test(item.original)
    ? "page"
    : "component",
  visualVerification: "pending-original-render",
}));
function previousRecords(filename, field) {
  const file = path.join(docs, filename);
  return fs.existsSync(file)
    ? JSON.parse(fs.readFileSync(file, "utf8"))[field] ?? []
    : [];
}
const operationRecords = preserveOperationAcceptance(
  operations,
  previousRecords("operation-inventory.json", "operations"),
);
const componentRecords = preserveComponentAcceptance(
  components,
  previousRecords("component-inventory.json", "components"),
);
fs.writeFileSync(
  path.join(docs, "operation-inventory.json"),
  JSON.stringify(
    {
      note: "Static API call inventory, not functional acceptance or a 100% coverage claim. Exported helpers may be included; dynamic/indirect calls need manual review.",
      apiModules: apiFiles.length,
      operations: operationRecords,
    },
    null,
    2,
  ) + "\n",
);
fs.writeFileSync(
  path.join(docs, "component-inventory.json"),
  JSON.stringify(
    { version: manifest.version, components: componentRecords },
    null,
    2,
  ) + "\n",
);
console.log(
  JSON.stringify({
    verifiedGeneratedAssets: manifest.generated.length,
    apiModules: apiFiles.length,
    exportedOperations: operations.length,
    operationsWithStaticConsumers: operations.filter(
      (op) => op.consumers.length,
    ).length,
    sourceComponents: components.length,
  }),
);
