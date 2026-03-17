import { useState, useEffect } from "react";
import { Radio, Select, Tooltip } from "@agentscope-ai/design";
import { InfoCircleOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import styles from "../../index.module.less";

type RoutingMode = "auto" | "nitro" | "free" | "floor" | "manual";

interface OpenRouterRoutingProps {
  models: Array<{ id: string; name: string }>;
  value?: string;
  onChange: (model: string) => void;
}

function parseRoutingFromModel(model: string | undefined): {
  mode: RoutingMode;
  baseModel: string;
} {
  if (!model) return { mode: "manual", baseModel: "" };
  if (model === "openrouter/auto") return { mode: "auto", baseModel: "" };
  if (model === "openrouter/free") return { mode: "free", baseModel: "" };
  if (model.endsWith(":nitro")) {
    return { mode: "nitro", baseModel: model.replace(/:nitro$/, "") };
  }
  if (model.endsWith(":floor")) {
    return { mode: "floor", baseModel: model.replace(/:floor$/, "") };
  }
  return { mode: "manual", baseModel: model };
}

function buildModel(mode: RoutingMode, baseModel: string): string {
  switch (mode) {
    case "auto":
      return "openrouter/auto";
    case "free":
      return "openrouter/free";
    case "nitro":
      return baseModel ? `${baseModel}:nitro` : "";
    case "floor":
      return baseModel ? `${baseModel}:floor` : "";
    case "manual":
      return baseModel;
  }
}

export function OpenRouterRouting({
  models,
  value,
  onChange,
}: OpenRouterRoutingProps) {
  const { t } = useTranslation();
  const parsed = parseRoutingFromModel(value);
  const [mode, setMode] = useState<RoutingMode>(parsed.mode);
  const [baseModel, setBaseModel] = useState(parsed.baseModel);

  useEffect(() => {
    const p = parseRoutingFromModel(value);
    setMode(p.mode);
    setBaseModel(p.baseModel);
  }, [value]);

  const handleModeChange = (newMode: RoutingMode) => {
    setMode(newMode);
    const result = buildModel(newMode, baseModel);
    if (result) onChange(result);
  };

  const handleModelSelect = (selected: string) => {
    setBaseModel(selected);
    const result = buildModel(mode, selected);
    if (result) onChange(result);
  };

  const needsModelPicker = mode === "nitro" || mode === "floor" || mode === "manual";

  // Filter out meta-models from the picker
  const pickableModels = models.filter(
    (m) => m.id !== "openrouter/auto" && m.id !== "openrouter/free",
  );

  return (
    <div className={styles.openrouterRouting}>
      <div className={styles.openrouterRoutingHeader}>
        <label className={styles.slotLabel}>
          {t("models.openrouterRouting")}
          <Tooltip title={t("models.openrouterRoutingInfo")}>
            <InfoCircleOutlined style={{ marginLeft: 4, cursor: "help" }} />
          </Tooltip>
        </label>
      </div>

      <Radio.Group
        value={mode}
        onChange={(e) => handleModeChange(e.target.value)}
        style={{ display: "flex", flexDirection: "column", gap: 6 }}
      >
        <Radio value="auto">{t("models.openrouterRoutingAuto")}</Radio>
        <Radio value="nitro">{t("models.openrouterRoutingNitro")}</Radio>
        <Radio value="free">{t("models.openrouterRoutingFree")}</Radio>
        <Radio value="floor">{t("models.openrouterRoutingFloor")}</Radio>
        <Radio value="manual">{t("models.openrouterRoutingManual")}</Radio>
      </Radio.Group>

      {needsModelPicker && (
        <Select
          style={{ width: "100%", marginTop: 8 }}
          placeholder={t("models.selectModel")}
          showSearch
          optionFilterProp="label"
          value={baseModel || undefined}
          onChange={handleModelSelect}
          options={pickableModels.map((m) => ({
            value: m.id,
            label: `${m.name} (${m.id})`,
          }))}
        />
      )}
    </div>
  );
}
