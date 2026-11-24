"use client";
import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import { api } from "@/lib/types";
import { Button } from "./ui/button";
import { columnTypeLabel } from "@/lib/column-data-types";

const providers = [
  ["groq", "Groq (free tier available)"],
  ["gemini", "Google Gemini (free tier available)"],
  ["openrouter", "OpenRouter"],
] as const;

type Suggestion = { type: string; rationale: string };

export function AiAssistPanel({
  fileId,
  column,
  disabled = false,
  onApply,
}: {
  fileId: string;
  column: string;
  disabled?: boolean;
  onApply: (type: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [provider, setProvider] = useState("groq");
  const [model, setModel] = useState("");
  const [key, setKey] = useState("");
  const [remember, setRemember] = useState(false);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);

  useEffect(() => {
    setProvider(localStorage.getItem("dataneat-assist-provider") || "groq");
    setModel(localStorage.getItem("dataneat-assist-model") || "");
    const stored = localStorage.getItem("dataneat-assist-key");
    const session = sessionStorage.getItem("dataneat-assist-key");
    setKey(stored || session || "");
    setRemember(Boolean(stored));
    setConsent(sessionStorage.getItem("dataneat-assist-consent") === "yes");
  }, []);

  function rememberKey(value: string) {
    if (remember) {
      localStorage.setItem("dataneat-assist-key", value);
      sessionStorage.removeItem("dataneat-assist-key");
    } else {
      sessionStorage.setItem("dataneat-assist-key", value);
      localStorage.removeItem("dataneat-assist-key");
    }
  }

  async function suggest() {
    setBusy(true);
    setError("");
    setSuggestion(null);
    try {
      localStorage.setItem("dataneat-assist-provider", provider);
      localStorage.setItem("dataneat-assist-model", model);
      sessionStorage.setItem("dataneat-assist-consent", "yes");
      rememberKey(key);
      const result = await api<{ suggestion: Suggestion }>("/assist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          file_id: fileId,
          column,
          provider,
          key,
          model,
          mode: "suggest_type",
          consent: true,
        }),
      });
      setSuggestion(result.suggestion);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ai-assist">
      <Button
        size="sm"
        variant="outline"
        disabled={disabled}
        aria-expanded={open}
        onClick={() => {
          setOpen((value) => !value);
          setError("");
        }}
      >
        <Sparkles size={14} aria-hidden="true" /> Suggest with AI
      </Button>
      {open && (
        <section className="ai-assist-panel" aria-label="Optional AI suggestion">
          <p>
            Optional. DataNeat sends only this column&apos;s name, detected type,
            issue kinds and up to 12 short sample values to the provider you
            choose. Your key is used for this request and is not stored on the
            server. No suggestion is applied without your confirmation.
          </p>
          <label className="setting">
            Provider
            <select
              value={provider}
              disabled={busy}
              onChange={(event) => setProvider(event.target.value)}
            >
              {providers.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="setting">
            Model (optional)
            <input
              value={model}
              disabled={busy}
              placeholder="Leave blank for the provider default"
              onChange={(event) => setModel(event.target.value)}
            />
          </label>
          <label className="setting">
            Your API key
            <input
              type="password"
              value={key}
              disabled={busy}
              autoComplete="off"
              placeholder="Your own provider key"
              onChange={(event) => setKey(event.target.value)}
            />
          </label>
          <label className="ai-assist-check">
            <input
              type="checkbox"
              checked={remember}
              disabled={busy}
              onChange={(event) => setRemember(event.target.checked)}
            />
            Remember this key on this device
          </label>
          <label className="ai-assist-check">
            <input
              type="checkbox"
              checked={consent}
              disabled={busy}
              onChange={(event) => setConsent(event.target.checked)}
            />
            I agree that these sample values may be sent to the selected
            provider.
          </label>
          <Button disabled={busy || !key || !consent} onClick={suggest}>
            <Sparkles size={14} aria-hidden="true" /> Suggest a data type
          </Button>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          {suggestion && (
            <div className="ai-assist-result" role="status">
              <p>
                Suggested type: <strong>{columnTypeLabel(suggestion.type)}</strong>
              </p>
              {suggestion.rationale && <p>{suggestion.rationale}</p>}
              <p>
                <small>
                  This is a suggestion, not a fact. Your values are unchanged
                  until you save the type, and you can undo it in History.
                </small>
              </p>
              <Button
                size="sm"
                disabled={busy || disabled}
                onClick={() => {
                  onApply(suggestion.type);
                  setOpen(false);
                }}
              >
                Use this type
              </Button>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
