"use strict";

const fs = require("fs");
const path = require("path");
const { branchRelation } = require("../branchRelation");
const { palaceByName, getMajorStarNames, getPalaceStarNamesFallback, validateChart } = require("../chartUtils");

const RULES_ROOT = path.join(__dirname, "..", "rules");
const TABLES_DIR = path.join(__dirname, "..", "tables");

function loadJson(rel) {
  return JSON.parse(fs.readFileSync(path.join(TABLES_DIR, rel), "utf8"));
}

function loadRulePack(ruleVersion) {
  const segs = String(ruleVersion).split("/").filter(Boolean);
  if (segs.length < 1) throw new Error("rule_version empty");
  const fileName = `${segs[segs.length - 1]}.json`;
  const dirs = segs.slice(0, -1);
  const full = path.join(RULES_ROOT, ...dirs, fileName);
  if (!fs.existsSync(full)) {
    throw new Error(`unknown rule_version: ${ruleVersion} (path ${full})`);
  }
  return JSON.parse(fs.readFileSync(full, "utf8"));
}

function starGroup(starName, groupings) {
  if (!starName) return groupings.default || "杂曜";
  return groupings[starName] || groupings.default || "杂曜";
}

function pairHarmony(g1, g2, pairTable) {
  const k1 = `${g1}|${g2}`;
  const k2 = `${g2}|${g1}`;
  const raw = pairTable.pairs[k1] ?? pairTable.pairs[k2];
  if (typeof raw === "number") return raw;
  return typeof pairTable.default === "number" ? pairTable.default : 0.42;
}

function primaryMingStars(chart, groupings) {
  const ming = palaceByName(chart, "命宫");
  const names = getMajorStarNames(ming, 2);
  if (names.length > 0) return names;
  if (chart.soul_palace && chart.soul_palace.soul) return [chart.soul_palace.soul];
  return [];
}

function primaryFuqiStars(chart, groupings) {
  const p = palaceByName(chart, "夫妻");
  return getPalaceStarNamesFallback(p, 2);
}

function scorePalacePair(chartL, leftName, chartR, rightName, check, pack, tag) {
  const pl = palaceByName(chartL, leftName);
  const pr = palaceByName(chartR, rightName);
  const hits = [];
  if (!pl || !pr || !pl.earthly_branch || !pr.earthly_branch) {
    hits.push({
      rule_id: check.id,
      dimension: "palace_alignment",
      effect: 0,
      evidence: { tag, left_palace: leftName, right_palace: rightName, note: "missing_branch_or_palace" },
    });
    return { points: 0, hits };
  }
  const rel = branchRelation(pl.earthly_branch, pr.earthly_branch);
  const f = pack.branch_relation_scores[rel] ?? 0.52;
  const pts = f * check.max_points;
  hits.push({
    rule_id: check.id,
    dimension: "palace_alignment",
    effect: Number(pts.toFixed(3)),
    evidence: {
      tag,
      left_chart: tag.includes("A_vs_B") ? "A" : "B",
      right_chart: tag.includes("A_vs_B") ? "B" : "A",
      left_palace: leftName,
      right_palace: rightName,
      left_branch: pl.earthly_branch,
      right_branch: pr.earthly_branch,
      relation: rel,
      factor: f,
    },
  });
  return { points: pts, hits };
}

function dimensionPalace(chartA, chartB, pack) {
  const hits = [];
  let acc = 0;
  for (const c of pack.palace_checks || []) {
    if (c.left_palace === c.right_palace) {
      const r = scorePalacePair(chartA, c.left_palace, chartB, c.right_palace, c, pack, "A_vs_B_once");
      acc += r.points;
      hits.push(...r.hits);
    } else {
      const r1 = scorePalacePair(chartA, c.left_palace, chartB, c.right_palace, c, pack, "A_vs_B");
      const r2 = scorePalacePair(chartB, c.left_palace, chartA, c.right_palace, c, pack, "B_vs_A");
      acc += (r1.points + r2.points) / 2;
      hits.push(...r1.hits, ...r2.hits);
    }
  }
  const cap = pack.dimension_caps.palace_alignment;
  const raw = Math.min(acc, cap);
  return { id: "palace_alignment", score: raw, max: cap, hits };
}

function starHarmonyPoints(starsA, starsB, groupings, pairTable, cap) {
  if (!starsA.length || !starsB.length) return { points: 0, harmony: null };
  const gA = starGroup(starsA[0], groupings);
  const gB = starGroup(starsB[0], groupings);
  const h = pairHarmony(gA, gB, pairTable);
  return { points: Math.min(h * cap, cap), harmony: h, gA, gB };
}

/** 主星和谐：仅「A 命宫主星组」与「B 夫妻宫主星组」同气（pair 表和谐系数），满分 = 维度 cap */
function dimensionStar(chartA, chartB, pack, groupings, pairTable) {
  const cap = pack.dimension_caps.star_harmony;
  const mingA = primaryMingStars(chartA, groupings);
  const fqB = primaryFuqiStars(chartB, groupings);
  const one = starHarmonyPoints(mingA, fqB, groupings, pairTable, cap);
  const raw = Number(one.points.toFixed(3));
  const hits = [
    {
      rule_id: "SH001",
      dimension: "star_harmony",
      effect: raw,
      evidence: {
        pair: "A_ming_B_fuqi",
        stars_a: mingA,
        stars_b: fqB,
        groups: [one.gA, one.gB],
        harmony: one.harmony,
      },
    },
  ];
  return {
    id: "star_harmony",
    score: raw,
    max: cap,
    hits,
    a_ming_b_fuqi_harmony: one.harmony,
    ming_ming_harmony: one.harmony,
    raw_score_before_clip: raw,
    raw_max_positive: cap,
    scoring_formula: "score = harmony(A命宫组, B夫妻宫组) * cap",
  };
}

function birthYearFromChart(chart) {
  const sd = chart.birth_info && chart.birth_info.solar_date;
  if (!sd) return null;
  const y = parseInt(String(sd).split(/[-/]/)[0], 10);
  return Number.isFinite(y) ? y : null;
}

function decadalPalaceAtAge(chart, age) {
  if (age == null || !Number.isFinite(age)) return null;
  for (const p of chart.palaces || []) {
    const r = p.decadal && p.decadal.range;
    if (!Array.isArray(r) || r.length < 2) continue;
    const lo = r[0];
    const hi = r[1];
    if (age >= lo && age <= hi) return p;
  }
  return null;
}

function palaceHasMutagen(chart, palaceName, mu) {
  const p = palaceByName(chart, palaceName);
  if (!p) return false;
  const buckets = [p.major_stars, p.minor_stars, p.adjective_stars].filter(Boolean);
  for (const arr of buckets) {
    for (const s of arr) {
      if (s && s.mutagen === mu) return true;
    }
  }
  return false;
}

function keyPalaceBranches(chart, palaceNames) {
  const out = {};
  for (const n of palaceNames) {
    const p = palaceByName(chart, n);
    out[n] = p && p.earthly_branch ? p.earthly_branch : null;
  }
  return out;
}

function collectMutagenPalaceBranches(chart, mutagen) {
  const branches = new Set();
  for (const p of chart.palaces || []) {
    const buckets = [p.major_stars, p.minor_stars, p.adjective_stars].filter(Boolean);
    let hit = false;
    for (const arr of buckets) {
      for (const s of arr) {
        if (s && s.mutagen === mutagen) {
          hit = true;
          break;
        }
      }
      if (hit) break;
    }
    if (hit && p.earthly_branch) branches.add(p.earthly_branch);
  }
  return branches;
}

function dimensionMutagen(chartA, chartB, pack) {
  const hits = [];
  let positive = 0;
  let negative = 0;
  const cfg = pack.mutagen_interaction || {};
  const targetPalaces = Array.isArray(cfg.target_palaces) && cfg.target_palaces.length > 0
    ? cfg.target_palaces
    : ["命宫", "夫妻", "福德"];
  const targetWeights = cfg.target_palace_weights || {};
  const dirWeights = cfg.direction_weights || {};
  const luPoint = Number(cfg.points && cfg.points.lu_hit) || 2;
  const jiPoint = Number(cfg.points && cfg.points.ji_hit) || 2.5;
  const matrix = {
    A_to_B: {},
    B_to_A: {},
  };
  const dirStats = {
    A_to_B: { lu_matched: false, ji_matched: false },
    B_to_A: { lu_matched: false, ji_matched: false },
  };

  const applyDirection = (sourceChart, targetChart, dirKey, dirLabel) => {
    const dirW = Number(dirWeights[dirKey] != null ? dirWeights[dirKey] : 1);
    const targetBranchMap = keyPalaceBranches(targetChart, targetPalaces);
    const luBranches = collectMutagenPalaceBranches(sourceChart, "禄");
    const jiBranches = collectMutagenPalaceBranches(sourceChart, "忌");

    for (const palaceName of targetPalaces) {
      const targetBranch = targetBranchMap[palaceName];
      const palaceW = Number(targetWeights[palaceName] != null ? targetWeights[palaceName] : 1);
      if (!targetBranch) {
        matrix[dirKey][palaceName] = {
          target_branch: null,
          lu: { matched: false, effect: 0 },
          ji: { matched: false, effect: 0 },
          note: "missing_target_branch",
        };
        hits.push({
          rule_id: `MJ_LU_${dirKey}_${palaceName}`,
          dimension: "mutagen_interaction",
          effect: 0,
          evidence: { direction: dirLabel, type: "positive", target_palace: palaceName, matched: false, note: "missing_target_branch" },
        });
        hits.push({
          rule_id: `MJ_JI_${dirKey}_${palaceName}`,
          dimension: "mutagen_interaction",
          effect: 0,
          evidence: { direction: dirLabel, type: "negative", target_palace: palaceName, matched: false, note: "missing_target_branch" },
        });
        continue;
      }

      const luMatched = luBranches.has(targetBranch);
      const luEffect = luMatched ? 1 : 0;
      if (luMatched) dirStats[dirKey].lu_matched = true;
      hits.push({
        rule_id: `MJ_LU_${dirKey}_${palaceName}`,
        dimension: "mutagen_interaction",
        effect: Number(luEffect.toFixed(3)),
        evidence: {
          direction: dirLabel,
          type: "positive",
          target_palace: palaceName,
          target_branch: targetBranch,
          source_lu_branches: Array.from(luBranches),
          matched: luMatched,
          palace_weight: palaceW,
          direction_weight: dirW,
        },
      });

      const jiMatched = jiBranches.has(targetBranch);
      const jiEffect = jiMatched ? -1 : 0;
      if (jiMatched) dirStats[dirKey].ji_matched = true;
      hits.push({
        rule_id: `MJ_JI_${dirKey}_${palaceName}`,
        dimension: "mutagen_interaction",
        effect: Number(jiEffect.toFixed(3)),
        evidence: {
          direction: dirLabel,
          type: "negative",
          target_palace: palaceName,
          target_branch: targetBranch,
          source_ji_branches: Array.from(jiBranches),
          matched: jiMatched,
          palace_weight: palaceW,
          direction_weight: dirW,
        },
      });

      matrix[dirKey][palaceName] = {
        target_branch: targetBranch,
        lu: {
          matched: luMatched,
          effect: Number(luEffect.toFixed(3)),
          source_branches: Array.from(luBranches),
        },
        ji: {
          matched: jiMatched,
          effect: Number(jiEffect.toFixed(3)),
          source_branches: Array.from(jiBranches),
        },
        palace_weight: palaceW,
        direction_weight: dirW,
      };
    }
  };

  applyDirection(chartA, chartB, "A_to_B", "A->B");
  applyDirection(chartB, chartA, "B_to_A", "B->A");

  positive =
    (dirStats.A_to_B.lu_matched ? 1 : 0) +
    (dirStats.B_to_A.lu_matched ? 1 : 0);
  negative =
    (dirStats.A_to_B.ji_matched ? 1 : 0) +
    (dirStats.B_to_A.ji_matched ? 1 : 0);

  const cap = pack.dimension_caps.mutagen_interaction;
  const rawDiff = positive - negative;
  // 业务口径：中性 50%；每多 1 个化禄方向 +25%，每多 1 个化忌方向 -25%
  const rawPercent = Math.max(0, Math.min(100, 50 + 25 * rawDiff));
  const raw = (rawPercent / 100) * cap;
  return {
    id: "mutagen_interaction",
    score: Number(raw.toFixed(3)),
    max: cap,
    hits,
    positive_score: Number(positive.toFixed(3)),
    negative_score: Number(negative.toFixed(3)),
    raw_score_before_clip: Number(rawPercent.toFixed(3)),
    raw_max_positive: 2,
    raw_max_negative: 2,
    raw_diff: Number(rawDiff.toFixed(3)),
    scoring_formula: "percent = clamp(50 + 25*(lu_count - ji_count), 0, 100)",
    direction_hits: dirStats,
    matrix,
  };
}

function resolveReferenceYear(opts) {
  const y = opts && opts.reference_year;
  const n = Number(y);
  if (Number.isFinite(n) && n >= 1900 && n <= 2200) return n;
  return new Date().getFullYear();
}

function ageInYear(chart, solarYear, opts, which) {
  const refY = resolveReferenceYear(opts);
  if (which === "a" && opts.reference_age_a != null) {
    const base = Number(opts.reference_age_a);
    if (Number.isFinite(base)) return base + (solarYear - refY);
  }
  if (which === "b" && opts.reference_age_b != null) {
    const base = Number(opts.reference_age_b);
    if (Number.isFinite(base)) return base + (solarYear - refY);
  }
  const by = birthYearFromChart(chart);
  if (by == null) return null;
  return solarYear - by;
}

function dimensionLifeRhythm(chartA, chartB, pack, opts) {
  const cap = pack.dimension_caps.life_rhythm;
  if (!pack.life_rhythm || !pack.life_rhythm.enabled) {
    return { id: "life_rhythm", score: 0, max: 0, hits: [], disabled: true };
  }
  const lrCfg = pack.life_rhythm;
  const years = Math.min(30, Math.max(1, Number(lrCfg.years) || 10));
  const refYear = resolveReferenceYear(opts);

  let sumF = 0;
  let counted = 0;
  const samples = [];
  for (let i = 0; i < years; i++) {
    const y = refYear + i;
    const ageA = ageInYear(chartA, y, opts, "a");
    const ageB = ageInYear(chartB, y, opts, "b");
    const pa = decadalPalaceAtAge(chartA, ageA);
    const pb = decadalPalaceAtAge(chartB, ageB);
    if (!pa || !pb || !pa.earthly_branch || !pb.earthly_branch) {
      samples.push({ year: y, note: "missing_decadal_palace" });
      continue;
    }
    const rel = branchRelation(pa.earthly_branch, pb.earthly_branch);
    const f = pack.branch_relation_scores[rel] ?? 0.52;
    sumF += f;
    counted += 1;
    if (samples.length < 5) {
      samples.push({
        year: y,
        age_a: ageA,
        age_b: ageB,
        palace_a: pa.name,
        palace_b: pb.name,
        branch_a: pa.earthly_branch,
        branch_b: pb.earthly_branch,
        relation: rel,
        factor: f,
      });
    }
  }

  const avg = counted > 0 ? sumF / counted : 0.52;
  const raw = Math.min(avg * cap, cap);
  const hits = [
    {
      rule_id: "LR001",
      dimension: "life_rhythm",
      effect: Number(raw.toFixed(3)),
      evidence: {
        reference_year: refYear,
        horizon_years: years,
        decadal_pairs_sampled: counted,
        average_branch_factor: Number(avg.toFixed(4)),
        samples,
      },
    },
  ];

  return { id: "life_rhythm", score: raw, max: cap, hits, disabled: false };
}

function spouseSpouseChong(chartA, chartB) {
  const a = palaceByName(chartA, "夫妻");
  const b = palaceByName(chartB, "夫妻");
  if (!a || !b) return false;
  return branchRelation(a.earthly_branch, b.earthly_branch) === "chong";
}

function computePenalty(chartA, chartB, pack, groupings, pairTable, starDim) {
  let pen = 0;
  const hits = [];
  const thr = pairTable.high_friction_threshold ?? 0.34;
  const crossHarm =
    starDim && typeof starDim.a_ming_b_fuqi_harmony === "number"
      ? starDim.a_ming_b_fuqi_harmony
      : starDim && typeof starDim.ming_ming_harmony === "number"
        ? starDim.ming_ming_harmony
        : null;
  if (crossHarm != null && crossHarm <= thr) {
    const p = -4;
    pen += p;
    hits.push({
      rule_id: "PN001",
      dimension: "penalty",
      effect: p,
      evidence: { reason: "A_ming_B_fuqi_high_friction", harmony: crossHarm, threshold: thr },
    });
  }
  if (spouseSpouseChong(chartA, chartB)) {
    const p = -3;
    pen += p;
    hits.push({
      rule_id: "PN002",
      dimension: "penalty",
      effect: p,
      evidence: { reason: "spouse_palace_chong" },
    });
  }
  const cap = pack.penalty_cap ?? 8;
  const clipped = Math.max(pen, -cap);
  if (clipped !== pen) {
    hits.push({ rule_id: "PN_CAP", dimension: "penalty", effect: 0, evidence: { note: "penalty_capped", cap: -cap } });
  }
  return { score: clipped, hits };
}

const WEIGHT_KEYS = ["palace_alignment", "star_harmony", "mutagen_interaction", "life_rhythm"];

function normalizeWeights(weights, lifeRhythmDisabled) {
  const w = { ...weights };
  if (lifeRhythmDisabled) {
    const lr = w.life_rhythm ?? 0;
    w.life_rhythm = 0;
    const sumRest = WEIGHT_KEYS.reduce((s, k) => s + (w[k] || 0), 0);
    if (sumRest > 0 && lr > 0) {
      const scale = 1 / (1 - lr);
      for (const k of WEIGHT_KEYS) {
        if (w[k] != null) w[k] *= scale;
      }
    }
  }
  const sum = WEIGHT_KEYS.reduce((s, k) => s + (w[k] || 0), 0);
  if (sum > 0 && Math.abs(sum - 1) > 0.001) {
    for (const k of WEIGHT_KEYS) {
      if (w[k] != null) w[k] = (w[k] || 0) / sum;
    }
  }
  return w;
}

function confidenceFromMeta(metaA, metaB) {
  let c = 1;
  const metas = [metaA, metaB].filter(Boolean);
  for (const m of metas) {
    const lr = m.longitude_resolution;
    if (lr && lr.source === "default") c -= 0.15;
    if (Array.isArray(m.warnings)) c -= Math.min(0.2, m.warnings.length * 0.05);
  }
  return Number(Math.max(0, Math.min(1, c)).toFixed(3));
}

function buildDimensionReasonSummary(dimension) {
  const relationZh = {
    sanhe: "三合",
    liuhe: "六合",
    same: "同宫同气",
    neutral: "中性",
    chong: "相冲",
  };
  const pairZh = {
    ming_ming: "命宫主星匹配",
    fuqi_fuqi: "夫妻宫风格匹配",
    A_ming_B_fuqi: "A命宫与B夫妻宫主星同气",
    A_fuqi_B_fuqi: "双方夫妻宫主星匹配",
    A_ming_B_ming: "双方命宫主星匹配",
    A_ming_B_fude: "A命宫与B福德宫主星匹配",
    B_ming_A_fuqi: "B命宫与A夫妻宫主星同气",
  };
  const palaceZh = {
    命宫: "命宫",
    夫妻: "夫妻宫",
    福德: "福德宫",
  };

  const formatEffect = (n) => {
    const v = Number(n || 0);
    const abs = Math.abs(v);
    const s = abs.toFixed(2).replace(/\.00$/, "");
    if (v > 0) return `+${s}`;
    if (v < 0) return `-${s}`;
    return "0";
  };

  const explainHit = (h) => {
    const e = h.evidence || {};
    const effText = `（${formatEffect(h.effect)}）`;
    if (dimension.id === "palace_alignment") {
      const left = e.left_palace ? (palaceZh[e.left_palace] || e.left_palace) : "关键宫位";
      const right = e.right_palace ? (palaceZh[e.right_palace] || e.right_palace) : "关键宫位";
      const rel = e.relation ? (relationZh[e.relation] || e.relation) : "有呼应";
      return `${left}${right}${rel}${effText}`;
    }
    if (dimension.id === "star_harmony") {
      const pairKey = e.pair;
      const pairDesc = pairZh[pairKey] || "主星组合匹配";
      const starsA = Array.isArray(e.stars_a) && e.stars_a.length ? e.stars_a.join("、") : "未取到";
      const starsB = Array.isArray(e.stars_b) && e.stars_b.length ? e.stars_b.join("、") : "未取到";
      return `${pairDesc}（${starsA} vs ${starsB}）${effText}`;
    }
    if (dimension.id === "mutagen_interaction") {
      if (e.note === "missing_target_branch") {
        return "关键宫位信息不完整，未计入该条";
      }
      const dir = e.direction || "";
      const target = e.target_palace ? (palaceZh[e.target_palace] || e.target_palace) : "";
      const matched = !!e.matched;
      if (e.type === "positive") {
        return matched ? `${dir} 的化禄落入${target}${effText}` : `${dir} 的化禄未落入${target}`;
      }
      if (e.type === "negative") {
        return matched ? `${dir} 的化忌落入${target}${effText}` : `${dir} 的化忌未落入${target}`;
      }
      return "四化关系未形成直接命中";
    }
    if (dimension.id === "life_rhythm") {
      return `未来十年大限节奏整体同频${effText}`;
    }
    return h.rule_id || "规则命中";
  };

  const pos = [];
  const neg = [];
  const neu = [];
  for (const h of dimension.hits || []) {
    const eff = Number(h.effect || 0);
    const label = explainHit(h);
    if (eff > 0) pos.push(label);
    else if (eff < 0) neg.push(label);
    else neu.push(label);
  }

  const uniq = (arr) => Array.from(new Set(arr));
  const posTop = uniq(pos).slice(0, 3);
  const negTop = uniq(neg).slice(0, 3);
  const neuTop = uniq(neu).slice(0, 2);

  let positiveText = posTop.length ? posTop.join("；") : "暂无明显加分点";
  let negativeText = negTop.length ? negTop.join("；") : "暂无明显扣分点";

  if (!posTop.length && dimension.id === "mutagen_interaction" && neuTop.length) {
    positiveText = "双方化禄未直接落在对方命宫/夫妻宫/福德宫";
  }
  if (!negTop.length && dimension.id === "mutagen_interaction" && neuTop.length) {
    negativeText = "双方化忌未直接落在对方命宫/夫妻宫/福德宫";
  }

  return {
    positive_reasons: pos,
    negative_reasons: neg,
    neutral_reasons: neu,
    display_text: `加分点：${positiveText}；扣分点：${negativeText}`,
  };
}

function computeCompat(chartA, chartB, options = {}) {
  const ruleVersion = options.rule_version || "compat/v1";
  const pack = options.rule_pack || loadRulePack(ruleVersion);
  const groupings = options.star_groupings || loadJson("star_groupings.json");
  const pairTable = options.star_pair_scores || loadJson("star_pair_scores.json");

  const errA = validateChart(chartA);
  const errB = validateChart(chartB);
  if (errA) throw new Error(`chart_a invalid: ${errA}`);
  if (errB) throw new Error(`chart_b invalid: ${errB}`);

  const lifeDisabled = !pack.life_rhythm || !pack.life_rhythm.enabled;
  const weights = normalizeWeights(pack.weights, lifeDisabled);

  const dimPalace = dimensionPalace(chartA, chartB, pack);
  const dimStar = dimensionStar(chartA, chartB, pack, groupings, pairTable);
  const dimMut = dimensionMutagen(chartA, chartB, pack);
  const lifeRhythmOpts = {
    ...(options.payload && typeof options.payload === "object" && options.payload !== null ? options.payload : {}),
    reference_year: options.reference_year ?? options.payload?.reference_year,
    reference_age_a: options.reference_age_a ?? options.payload?.reference_age_a,
    reference_age_b: options.reference_age_b ?? options.payload?.reference_age_b,
  };
  const dimRhythm = dimensionLifeRhythm(chartA, chartB, pack, lifeRhythmOpts);

  const penalty = computePenalty(chartA, chartB, pack, groupings, pairTable, dimStar);

  const dims = [dimPalace, dimStar, dimMut, dimRhythm];
  let total = 0;
  for (const d of dims) {
    const wKey = d.id;
    const w = weights[wKey] ?? 0;
    const max = d.max || 0;
    if (max <= 0) continue;
    const u = Math.max(0, Math.min(1, d.score / max));
    total += w * u * 100;
  }

  const scoreRaw = total + (penalty.score || 0);
  const score = Math.max(0, Math.min(100, Math.round(scoreRaw)));

  const allHits = [...dimPalace.hits, ...dimStar.hits, ...dimMut.hits, ...dimRhythm.hits, ...penalty.hits];
  const dimensions = dims.map((d) => {
    const base = {
      id: d.id,
      score: Number(d.score.toFixed(3)),
      max: d.max,
      hits: d.hits,
      ...(d.positive_score != null ? { positive_score: d.positive_score } : {}),
      ...(d.negative_score != null ? { negative_score: d.negative_score } : {}),
      ...(d.raw_score_before_clip != null ? { raw_score_before_clip: d.raw_score_before_clip } : {}),
      ...(d.raw_max_positive != null ? { raw_max_positive: d.raw_max_positive } : {}),
      ...(d.raw_max_negative != null ? { raw_max_negative: d.raw_max_negative } : {}),
      ...(d.raw_diff != null ? { raw_diff: d.raw_diff } : {}),
      ...(d.scoring_formula != null ? { scoring_formula: d.scoring_formula } : {}),
      ...(d.direction_hits != null ? { direction_hits: d.direction_hits } : {}),
      ...(d.matrix != null ? { matrix: d.matrix } : {}),
    };
    return {
      ...base,
      reason_summary: buildDimensionReasonSummary(base),
    };
  });

  return {
    score,
    confidence: confidenceFromMeta(options.meta_a, options.meta_b),
    rule_version: pack.id || ruleVersion,
    dimensions,
    hits: allHits,
    penalty_total: penalty.score,
  };
}

module.exports = {
  computeCompat,
  loadRulePack,
};
