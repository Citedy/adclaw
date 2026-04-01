import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  Button,
  Input,
  Steps,
  Card,
  message,
  Space,
  Typography,
  Select,
  Alert,
} from "antd";
import {
  Rocket,
  Key,
  MessageCircle,
  CheckCircle,
  ExternalLink,
  Cpu,
  Search,
} from "lucide-react";
import { request } from "../../api/request";
import styles from "./index.module.less";

const { Title, Text, Paragraph } = Typography;

interface CitedyStatus {
  configured: boolean;
  api_key_prefix?: string;
  balance?: { credits: number; status: string } | null;
  developer_url: string;
  billing_url: string;
}

interface ModelInfo {
  id: string;
  name: string;
}

interface ProviderInfo {
  id: string;
  name: string;
  models: ModelInfo[];
  current_api_key: string;
  current_base_url: string;
  is_local: boolean;
  needs_base_url: boolean;
}

interface ActiveModels {
  active_llm: { provider_id: string; model: string } | null;
}

interface SearchStatus {
  exa: { configured: boolean; api_key_prefix?: string | null };
  xai: { configured: boolean; api_key_prefix?: string | null };
}

// Recommended providers for the wizard (order matters)
const WIZARD_PROVIDERS = [
  "aliyun-intl",
  "openrouter",
  "openai",
  "anthropic",
  "zai",
  "xai",
  "aliyun-codingplan",
  "ollama",
];

export default function WelcomePage() {
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState(0);
  const [apiKey, setApiKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [citedyStatus, setCitedyStatus] = useState<CitedyStatus | null>(null);

  // LLM state
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>("aliyun-intl");
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [llmApiKey, setLlmApiKey] = useState("");
  const [savingLlm, setSavingLlm] = useState(false);
  const [llmConfigured, setLlmConfigured] = useState(false);

  // Search state
  const [exaKey, setExaKey] = useState("");
  const [xaiKey, setXaiKey] = useState("");
  const [savingSearch, setSavingSearch] = useState(false);
  const [searchStatus, setSearchStatus] = useState<SearchStatus | null>(null);

  useEffect(() => {
    request<CitedyStatus>("/citedy/status").then((res) => {
      setCitedyStatus(res);
      if (res.configured) setCurrentStep(1);
    });
    request<ProviderInfo[]>("/models").then((res) => {
      setProviders(res);
    });
    request<ActiveModels>("/models/active").then((res) => {
      if (res.active_llm?.provider_id) {
        setLlmConfigured(true);
        setSelectedProvider(res.active_llm.provider_id);
        setSelectedModel(res.active_llm.model);
      }
    });
    request<SearchStatus>("/search/status").then((res) => {
      setSearchStatus(res);
    });
  }, []);

  const handleSaveApiKey = async () => {
    if (!apiKey.trim()) {
      message.warning("Please enter your Citedy API key");
      return;
    }
    setSaving(true);
    try {
      await request("/citedy/save-api-key", {
        method: "POST",
        body: JSON.stringify({ api_key: apiKey.trim() }),
        headers: { "Content-Type": "application/json" },
      });
      message.success("API key saved successfully!");
      setCurrentStep(1);
      const status = await request<CitedyStatus>("/citedy/status");
      setCitedyStatus(status);
    } catch {
      message.error("Failed to save API key");
    } finally {
      setSaving(false);
    }
  };

  const wizardProviders = providers.filter((p) =>
    WIZARD_PROVIDERS.includes(p.id)
  );
  const currentProvider = providers.find((p) => p.id === selectedProvider);

  const handleSaveLlm = async () => {
    if (!selectedProvider || !selectedModel) {
      message.warning("Please select a provider and model");
      return;
    }
    if (!currentProvider?.is_local && !llmApiKey.trim() && !currentProvider?.current_api_key) {
      message.warning("Please enter an API key for this provider");
      return;
    }
    setSavingLlm(true);
    try {
      if (llmApiKey.trim()) {
        await request(`/models/${selectedProvider}/config`, {
          method: "PUT",
          body: JSON.stringify({ api_key: llmApiKey.trim() }),
          headers: { "Content-Type": "application/json" },
        });
      }
      await request("/models/active", {
        method: "PUT",
        body: JSON.stringify({
          provider_id: selectedProvider,
          model: selectedModel,
        }),
        headers: { "Content-Type": "application/json" },
      });
      message.success("LLM configured!");
      setLlmConfigured(true);
      setCurrentStep(2);
    } catch {
      message.error("Failed to configure LLM");
    } finally {
      setSavingLlm(false);
    }
  };

  const handleSaveSearch = async () => {
    if (!exaKey.trim() && !xaiKey.trim()) {
      message.warning("Enter at least one search API key");
      return;
    }
    setSavingSearch(true);
    try {
      const body: Record<string, string> = {};
      if (exaKey.trim()) body.exa_api_key = exaKey.trim();
      if (xaiKey.trim()) body.xai_api_key = xaiKey.trim();
      const res = await request<SearchStatus>("/search/save-keys", {
        method: "POST",
        body: JSON.stringify(body),
        headers: { "Content-Type": "application/json" },
      });
      setSearchStatus(res);
      message.success("Search keys saved!");
      setCurrentStep(3);
    } catch {
      message.error("Failed to save search keys");
    } finally {
      setSavingSearch(false);
    }
  };

  const handleFinish = () => {
    localStorage.setItem("adclaw_welcome_seen", "true");
    navigate("/chat", { replace: true });
  };

  const providerHints: Record<string, React.ReactNode> = {
    openrouter: "One key for all models — Claude, GPT, Gemini, Llama, etc. Get key at openrouter.ai",
    openai: "Direct access to GPT-5.4, Codex, o3, o4-mini, GPT-4o. Get key at platform.openai.com",
    anthropic: "Claude Opus 4.6, Sonnet 4.6, Haiku 4.5. Get key at console.anthropic.com",
    xai: "Grok 4.1 Fast — $0.20/1M input. Get key at console.x.ai",
    "aliyun-intl": <>qwen3.5-plus, kimi-k2.5, glm-5, MiniMax-M2.5, qwen3-max, qwen3-coder-next, qwen3-coder-plus. <a href="https://www.alibabacloud.com/campaign/benefits?referral_code=A9EXYQ" target="_blank" rel="noopener">Join for $3-10 &rarr;</a></>,
    "aliyun-codingplan": "Same models as Aliyun Intl but China endpoint.",
    ollama: "Run models locally. No API key needed. Install at ollama.com",
    zai: <>GLM-5, GLM-5 Turbo, GLM-4.7, GLM-4.6, GLM-4.5 — direct from Z.AI. <a href="https://z.ai/subscribe?ic=DXX7MK5MJT" target="_blank" rel="noopener">$10/month &rarr;</a></>,
    moonshot: "Kimi K2.5, K2 Thinking, Moonshot V1. Get key at platform.moonshot.ai",
  };

  const searchConfigured =
    searchStatus?.exa?.configured || searchStatus?.xai?.configured;

  return (
    <div className={styles.welcomeContainer}>
      <div className={styles.welcomeContent}>
        <div className={styles.heroSection}>
          <img
            src="/logo.png"
            alt="AdClaw"
            className={styles.logo}
          />
          <Title level={1} className={styles.title}>
            Welcome to AdClaw
          </Title>
          <Paragraph className={styles.subtitle}>
            Your AI Marketing Assistant powered by Citedy.
            <br />
            SEO articles, trend scouting, lead magnets, AI videos — all in one
            bot.
          </Paragraph>
        </div>

        <Steps
          current={currentStep}
          className={styles.steps}
          items={[
            { title: "Citedy API Key", icon: <Key size={18} /> },
            { title: "Choose LLM", icon: <Cpu size={18} /> },
            { title: "Web Search", icon: <Search size={18} /> },
            { title: "Connect & Start", icon: <CheckCircle size={18} /> },
          ]}
        />

        <div className={styles.stepContent}>
          {currentStep === 0 && (
            <Card className={styles.stepCard}>
              <Title level={4}>Step 1: Get your Citedy API Key</Title>
              <Paragraph>
                AdClaw uses Citedy for SEO tools, content generation, and
                marketing automation. You need a free API key to get started.
              </Paragraph>
              <Space direction="vertical" size="middle" style={{ width: "100%" }}>
                <Button
                  type="primary"
                  size="large"
                  icon={<ExternalLink size={16} />}
                  onClick={() =>
                    window.open(
                      citedyStatus?.developer_url ||
                        "https://www.citedy.com/developer",
                      "_blank"
                    )
                  }
                >
                  Get Free API Key
                </Button>
                <Input.Password
                  size="large"
                  placeholder="Paste your citedy_agent_... key here"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  onPressEnter={handleSaveApiKey}
                />
                <Button
                  type="primary"
                  size="large"
                  loading={saving}
                  onClick={handleSaveApiKey}
                  block
                >
                  Save API Key
                </Button>
                <Button type="link" onClick={() => setCurrentStep(1)}>
                  Skip for now
                </Button>
              </Space>
            </Card>
          )}

          {currentStep === 1 && (
            <Card className={styles.stepCard}>
              <Title level={4}>Step 2: Choose your LLM Provider</Title>
              <Paragraph>
                AdClaw needs a language model to generate responses. Pick a
                provider and enter your API key.
              </Paragraph>

              {citedyStatus?.configured && (
                <Alert
                  type="success"
                  showIcon
                  icon={<CheckCircle size={16} />}
                  message={
                    <>
                      Citedy API key configured
                      {citedyStatus.balance && (
                        <Text type="secondary">
                          {" — "}{citedyStatus.balance.credits.toLocaleString()} credits
                        </Text>
                      )}
                    </>
                  }
                  style={{ marginBottom: 16 }}
                />
              )}

              <Space direction="vertical" size="middle" style={{ width: "100%" }}>
                <Select
                  size="large"
                  placeholder="Select LLM provider..."
                  style={{ width: "100%" }}
                  listHeight={300}
                  value={selectedProvider || undefined}
                  onChange={(val) => {
                    setSelectedProvider(val);
                    setSelectedModel("");
                    setLlmApiKey("");
                  }}
                  options={wizardProviders.map((p) => ({
                    value: p.id,
                    label: (
                      <span>
                        <strong>{p.name}</strong>
                        {p.id === "aliyun-intl" && (
                          <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                            Recommended
                          </Text>
                        )}
                      </span>
                    ),
                  }))}
                />

                {selectedProvider && providerHints[selectedProvider] && (
                  <Alert
                    type="info"
                    message={providerHints[selectedProvider]}
                    style={{ fontSize: 13 }}
                  />
                )}

                {currentProvider && currentProvider.models.length > 0 && (
                  <Select
                    size="large"
                    placeholder="Select model..."
                    style={{ width: "100%" }}
                    value={selectedModel || undefined}
                    onChange={setSelectedModel}
                    options={currentProvider.models.map((m) => ({
                      value: m.id,
                      label: m.name,
                    }))}
                  />
                )}

                {currentProvider && !currentProvider.is_local && (
                  <Input.Password
                    size="large"
                    placeholder={`Enter ${currentProvider.name} API key`}
                    value={llmApiKey}
                    onChange={(e) => setLlmApiKey(e.target.value)}
                  />
                )}

                <Space>
                  <Button
                    type="primary"
                    size="large"
                    loading={savingLlm}
                    onClick={handleSaveLlm}
                    disabled={!selectedProvider || !selectedModel}
                  >
                    Save & Continue
                  </Button>
                  <Button size="large" onClick={() => setCurrentStep(2)}>
                    Skip
                  </Button>
                  <Button
                    type="link"
                    onClick={() => navigate("/models")}
                  >
                    Advanced settings
                  </Button>
                </Space>
              </Space>
            </Card>
          )}

          {currentStep === 2 && (
            <Card className={styles.stepCard}>
              <Title level={4}>Step 3: Enable Web Search</Title>
              <Paragraph>
                Without search, your AI agent is blind to the internet.
                Add at least one search key so AdClaw can find real-time
                information, research competitors, and discover trends.
              </Paragraph>

              {llmConfigured && (
                <Alert
                  type="success"
                  showIcon
                  icon={<CheckCircle size={16} />}
                  message={`LLM configured: ${selectedModel || "ready"}`}
                  style={{ marginBottom: 16 }}
                />
              )}

              <Space direction="vertical" size="middle" style={{ width: "100%" }}>
                <div>
                  <Text strong>Exa Search</Text>
                  <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                    AI-powered web, code & people search
                  </Text>
                  <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
                    <Input.Password
                      size="large"
                      placeholder="Exa API key"
                      value={exaKey}
                      onChange={(e) => setExaKey(e.target.value)}
                      style={{ flex: 1 }}
                    />
                    <Button
                      size="large"
                      icon={<ExternalLink size={14} />}
                      onClick={() =>
                        window.open("https://dashboard.exa.ai/api-keys", "_blank")
                      }
                    >
                      Get Key
                    </Button>
                  </div>
                  {searchStatus?.exa?.configured && (
                    <Text type="success" style={{ fontSize: 12 }}>
                      <CheckCircle size={12} style={{ marginRight: 4 }} />
                      Configured ({searchStatus.exa.api_key_prefix})
                    </Text>
                  )}
                </div>

                <div>
                  <Text strong>xAI (Grok)</Text>
                  <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                    Web search + X/Twitter search (via Grok)
                  </Text>
                  <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
                    <Input.Password
                      size="large"
                      placeholder="xAI API key (xai-...)"
                      value={xaiKey}
                      onChange={(e) => setXaiKey(e.target.value)}
                      style={{ flex: 1 }}
                    />
                    <Button
                      size="large"
                      icon={<ExternalLink size={14} />}
                      onClick={() =>
                        window.open("https://console.x.ai", "_blank")
                      }
                    >
                      Get Key
                    </Button>
                  </div>
                  {searchStatus?.xai?.configured && (
                    <Text type="success" style={{ fontSize: 12 }}>
                      <CheckCircle size={12} style={{ marginRight: 4 }} />
                      Configured ({searchStatus.xai.api_key_prefix})
                    </Text>
                  )}
                </div>

                <Space>
                  <Button
                    type="primary"
                    size="large"
                    loading={savingSearch}
                    onClick={handleSaveSearch}
                    disabled={!exaKey.trim() && !xaiKey.trim()}
                  >
                    Save & Continue
                  </Button>
                  <Button size="large" onClick={() => setCurrentStep(3)}>
                    {searchConfigured ? "Continue" : "Skip"}
                  </Button>
                </Space>

                {!searchConfigured && (
                  <Alert
                    type="warning"
                    message="Without search keys, AdClaw cannot look up real-time information from the web."
                    style={{ fontSize: 13 }}
                  />
                )}
              </Space>
            </Card>
          )}

          {currentStep === 3 && (
            <Card className={styles.stepCard}>
              <Title level={4}>Step 4: Connect & Start</Title>

              {llmConfigured && (
                <Alert
                  type="success"
                  showIcon
                  icon={<CheckCircle size={16} />}
                  message={`LLM configured: ${selectedModel || "ready"}`}
                  style={{ marginBottom: 8 }}
                />
              )}
              {searchConfigured && (
                <Alert
                  type="success"
                  showIcon
                  icon={<CheckCircle size={16} />}
                  message={
                    [
                      searchStatus?.exa?.configured && "Exa search",
                      searchStatus?.xai?.configured && "xAI search",
                    ]
                      .filter(Boolean)
                      .join(" + ") + " enabled"
                  }
                  style={{ marginBottom: 16 }}
                />
              )}

              <Paragraph>
                Optionally connect a Telegram bot to chat with AdClaw from your
                phone — or jump straight to the web chat.
              </Paragraph>
              <Space size="middle">
                <Button
                  size="large"
                  icon={<MessageCircle size={16} />}
                  onClick={() => navigate("/channels")}
                >
                  Setup Telegram
                </Button>
                <Button type="primary" size="large" onClick={handleFinish}>
                  <Rocket size={16} style={{ marginRight: 8 }} />
                  Get Started!
                </Button>
              </Space>
            </Card>
          )}
        </div>

        {currentStep < 3 && (
          <div className={styles.skipSection}>
            <Button type="link" onClick={handleFinish}>
              Skip setup — go to chat
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
