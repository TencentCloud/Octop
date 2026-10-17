import { useTranslation } from "react-i18next";
import { ExternalLink, Variable } from "lucide-react";
import { TabPanelHeader } from "../../AdvancedSettings/TabPanelHeader";

interface PageHeaderProps {
  className?: string;
}

export function PageHeader({ className }: PageHeaderProps) {
  const { t } = useTranslation();

  return (
    <div className={className}>
      <TabPanelHeader
        icon={<Variable size={22} />}
        title={t("environments.title")}
        description={
          <>
            {t("environments.description")}
            <p style={{ marginTop: 8, marginBottom: 0, fontSize: 13 }}>
              {t("environments.secretGuide")}{" "}
              <a
                href="about:blank"
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  color: "var(--fn-text-brand)",
                  textDecoration: "none",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 3,
                }}
              >
                {t("environments.secretGuideLink")}
                <ExternalLink size={12} />
              </a>
            </p>
          </>
        }
      />
    </div>
  );
}
