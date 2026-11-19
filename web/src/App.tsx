import { localizeTree, metadata, type Locale } from "./localization";
import { ReservationCard } from "./ReservationCard";
import { GuidedPanel } from "./GuidedPanel";
import {
  acceptSnapshot,
  availabilityLabel,
  currentView,
  remaining,
  productImage,
} from "./projection";
import { SessionStartGate } from "./session-start";
import { useCallback, useEffect, useRef, useState } from "react";
import { useConversation } from "@elevenlabs/react";
import {
  api,
  ApiError,
  clock as formatClock,
  date as formatDate,
  displayError,
  euro as formatEuro,
} from "./safety";
import type {
  Config,
  GuidedAction,
  GuidedScenario,
  GuidedState,
  SessionState,
  SessionToken,
  TranscriptLine,
} from "./types";

const eventLabels: Record<string, string> = {
  search: "Cerca de peces",
  check: "Comprovació de variant",
  reserve: "Reserva d’una peça",
  operator_retry: "Reintent de l’operador",
  decline: "Reserva rebutjada",
};
function Icon({
  name,
}: {
  name: "mic" | "phone" | "speaker" | "arrow" | "check";
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {name === "mic" ? (
        <>
          <rect x="9" y="3" width="6" height="12" rx="3" />
          <path d="M5 11a7 7 0 0014 0M12 18v3M8 21h8" />
        </>
      ) : name === "phone" ? (
        <path d="M4 3h4l2 5-3 2a16 16 0 007 7l2-3 5 2v4c-9 3-20-8-17-17Z" />
      ) : name === "speaker" ? (
        <>
          <path d="M4 9h4l5-4v14l-5-4H4ZM17 8a6 6 0 010 8M20 5a10 10 0 010 14" />
        </>
      ) : name === "check" ? (
        <path d="m5 12 4 4L19 6" />
      ) : (
        <path d="M4 12h16m-6-6 6 6-6 6" />
      )}
    </svg>
  );
}
function Meter({ value, label }: { value: number; label: string }) {
  return (
    <div className="meter-wrap">
      <span>{label}</span>
      <meter
        min={0}
        max={1}
        value={Math.min(1, Math.max(0, value))}
        aria-label={label}
      />
    </div>
  );
}

export default function App() {
  const [locale, setLocale] = useState<Locale>("en");
  const euro = (value: number) => formatEuro(value, locale);
  const date = (value: string) => formatDate(value, locale);
  const clock = (value: number) => formatClock(value, locale);
  useEffect(() => {
    document.documentElement.lang = locale;
    document.title = metadata[locale].title;
    document
      .querySelector('meta[name="description"]')
      ?.setAttribute("content", metadata[locale].description);
  }, [locale]);
  const [config, setConfig] = useState<Config | null>(null),
    [scenario, setScenario] = useState("normal"),
    [gate, setGate] = useState(false),
    [code, setCode] = useState("");
  const [liveState, setState] = useState<SessionState | null>(null),
    [pollError, setPollError] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [retrying, setRetrying] = useState(false);
  const [guided, setGuided] = useState<GuidedState | null>(null);
  const [guideBusy, setGuideBusy] = useState(false);
  const [guideRestoring, setGuideRestoring] = useState(false);
  const guidePending = useRef(false);
  const guideRestore = useRef<AbortController | null>(null);
  const guideEntry = useRef<HTMLButtonElement>(null);
  const [transcript, setTranscript] = useState<TranscriptLine[]>([]),
    [micReady, setMicReady] = useState(false),
    [micTesting, setMicTesting] = useState(false),
    [micPending, setMicPending] = useState(false),
    [cancelling, setCancelling] = useState(false),
    [device, setDevice] = useState("Microfon del navegador");
  const [speakerTested, setSpeakerTested] = useState(false),
    [heard, setHeard] = useState(false),
    [volume, setVolume] = useState(0.85),
    [input, setInput] = useState(0),
    [output, setOutput] = useState(0),
    [outputSeen, setOutputSeen] = useState(false);
  const [audioHint, setAudioHint] = useState(""),
    [refresh, setRefresh] = useState(0);
  const diagnostic = useRef<{
    stream: MediaStream;
    context: AudioContext;
    frame: number;
    timer: number;
  } | null>(null);
  const startGate = useRef(new SessionStartGate());
  const expectedSession = useRef<string | null>(null);
  const [now, setNow] = useState(Date.now() / 1000);
  const [operatorOpen, setOperatorOpen] = useState(false);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(timer);
  }, []);
  const micGeneration = useRef(0);
  const permissionTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hasSession = useRef(false),
    starting = useRef(false),
    timeout = useRef<ReturnType<typeof setTimeout> | null>(null),
    transcriptEnd = useRef<HTMLDivElement>(null);
  const stopDiagnostic = useCallback(() => {
    micGeneration.current += 1;
    if (permissionTimer.current) clearTimeout(permissionTimer.current);
    setMicPending(false);
    const d = diagnostic.current;
    if (d) {
      cancelAnimationFrame(d.frame);
      clearTimeout(d.timer);
      d.stream.getTracks().forEach((t) => t.stop());
      void d.context.close();
      diagnostic.current = null;
    }
    setMicTesting(false);
    setInput(0);
  }, []);
  const endBackend = useCallback(async () => {
    if (!hasSession.current) return;
    try {
      await api("/session/end", null);
      hasSession.current = false;
      setRefresh((n) => n + 1);
    } catch (e) {
      setError(displayError(e));
    }
  }, []);
  const conversation = useConversation({
    volume,
    onConnect: () => {
      if (timeout.current) clearTimeout(timeout.current);
      starting.current = false;
      setBusy(false);
      setAudioHint(
        "Connectat. Comprova que sents l’Ona; la connexió no confirma que l’àudio sigui audible.",
      );
    },
    onDisconnect: () => {
      if (timeout.current) clearTimeout(timeout.current);
      if (!startGate.current.pending) {
        starting.current = false;
        setBusy(false);
      }
      setInput(0);
      setOutput(0);
      if (!startGate.current.pending) void endBackend();
    },
    onError: () => {
      conversation.endSession();
      if (timeout.current) clearTimeout(timeout.current);
      starting.current = false;
      setBusy(false);
      setError(
        "No s’ha pogut mantenir la conversa de veu. Revisa el micròfon i la sortida d’àudio, tanca la sessió i torna-ho a provar.",
      );
      void endBackend();
    },
    onMessage: (message) => {
      if (message.role !== "user" && message.role !== "agent") return;
      const line = {
        id: message.role + ":" + (message.response_id ?? message.event_id),
        role: message.role,
        message: message.message,
      } as TranscriptLine;
      setTranscript((lines) => {
        const i = lines.findIndex((l) => l.id === line.id);
        return i < 0
          ? [...lines, line]
          : lines.map((l, n) => (n === i ? line : l));
      });
    },
  });
  const connected = conversation.status === "connected",
    connecting = busy || conversation.status === "connecting",
    active = connected || connecting;
  const loadConfig = useCallback(async () => {
    try {
      const c = await api<Config>("/config");
      setConfig(c);
      setGate(c.access_required);
      setError("");
    } catch (e) {
      setError(displayError(e));
    }
  }, []);
  useEffect(() => {
    void loadConfig();
  }, [loadConfig]);
  useEffect(() => {
    if (!config || gate || window.location.hash !== "#guided") return;
    const controller = new AbortController();
    guideRestore.current = controller;
    setGuideRestoring(true);
    void api<GuidedState | null>("/guided", undefined, controller.signal)
      .then((snapshot) => {
        if (!controller.signal.aborted) setGuided(snapshot);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(displayError(e));
      })
      .finally(() => {
        if (guideRestore.current === controller) {
          guideRestore.current = null;
          setGuideRestoring(false);
        }
      });
    return () => controller.abort();
  }, [config, gate]);
  useEffect(() => {
    if (!config || gate) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await api<SessionState>(
          "/session",
          undefined,
          controller.signal,
        );
        if (controller.signal.aborted) return;
        if (startGate.current.pending) return;
        setState((current) =>
          acceptSnapshot(current, next, expectedSession.current),
        );
        setPollError("");
        hasSession.current = next.session?.status === "active";
      } catch (e) {
        if (controller.signal.aborted) return;
        setPollError(displayError(e));
        setState(null);
        if (e instanceof ApiError) {
          if (e.code === "session_expired" || e.code === "session_required")
            hasSession.current = false;
          if (e.code === "access_required") setGate(true);
        }
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(poll, 1200);
      }
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [config, gate, refresh]);
  useEffect(() => {
    if (!connected) return;
    const interval = setInterval(() => {
      setInput(conversation.getInputVolume());
      const level = conversation.getOutputVolume();
      setOutput(level);
      if (level > 0.015) setOutputSeen(true);
    }, 100);
    const noOutput = setTimeout(
      () =>
        setAudioHint(
          "Si no sents l’Ona, comprova el volum i la sortida del navegador. Pots tornar a provar l’altaveu; si cal, acaba la trucada i reconnecta.",
        ),
      20000,
    );
    return () => {
      clearInterval(interval);
      clearTimeout(noOutput);
    };
  }, [connected, conversation.getInputVolume, conversation.getOutputVolume]);
  useEffect(() => {
    transcriptEnd.current?.scrollIntoView({ block: "nearest" });
  }, [transcript]);
  useEffect(
    () => () => {
      startGate.current.cancel();
      conversation.endSession();
      if (!startGate.current.pending) void endBackend();
      stopDiagnostic();
      if (timeout.current) clearTimeout(timeout.current);
    },
    [stopDiagnostic, conversation.endSession, endBackend],
  );
  async function testMic() {
    setError("");
    stopDiagnostic();
    const generation = micGeneration.current;
    setMicReady(false);
    setMicPending(true);
    permissionTimer.current = setTimeout(() => {
      stopDiagnostic();
      setError(
        "Encara no hem rebut permís de micròfon. Revisa l’avís del navegador i torna-ho a provar; la prova ha deixat d’esperar.",
      );
    }, 15000);
    let stream: MediaStream | undefined;
    let context: AudioContext | undefined;
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error("unsupported");
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (generation !== micGeneration.current) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      context = new AudioContext();
      await context.resume();
      if (generation !== micGeneration.current) {
        stream.getTracks().forEach((t) => t.stop());
        void context.close();
        return;
      }
      if (context.state !== "running") throw new Error("suspended");
      if (permissionTimer.current) clearTimeout(permissionTimer.current);
      setMicPending(false);
      const analyser = context.createAnalyser();
      analyser.fftSize = 256;
      context.createMediaStreamSource(stream).connect(analyser);
      const values = new Uint8Array(analyser.fftSize);
      const d = { stream, context, frame: 0, timer: 0 };
      diagnostic.current = d;
      setDevice(stream.getAudioTracks()[0]?.label || "Micròfon del navegador");
      setMicReady(true);
      setMicTesting(true);
      function tick() {
        if (diagnostic.current !== d) return;
        analyser.getByteTimeDomainData(values);
        setInput(
          Math.min(
            1,
            Math.sqrt(
              values.reduce((sum, n) => sum + ((n - 128) / 128) ** 2, 0) /
                values.length,
            ) * 5,
          ),
        );
        d.frame = requestAnimationFrame(tick);
      }
      tick();
      d.timer = window.setTimeout(stopDiagnostic, 12000);
    } catch {
      stream?.getTracks().forEach((t) => t.stop());
      if (context && context.state !== "closed") void context.close();
      if (generation !== micGeneration.current) return;
      if (permissionTimer.current) clearTimeout(permissionTimer.current);
      setMicPending(false);
      setMicReady(false);
      setError(
        "No podem accedir al micròfon. Permet-ne l’accés a la barra d’adreces, revisa el dispositiu i torna a provar-lo. Cal HTTPS o localhost.",
      );
    }
  }
  async function testSpeaker() {
    setError("");
    let context: AudioContext | undefined;
    try {
      context = new AudioContext();
      await context.resume();
      if (context.state !== "running") throw new Error("blocked");
      const osc = context.createOscillator(),
        gain = context.createGain();
      osc.connect(gain);
      gain.connect(context.destination);
      osc.frequency.value = 440;
      gain.gain.setValueAtTime(0, context.currentTime);
      gain.gain.linearRampToValueAtTime(
        0.12 * volume,
        context.currentTime + 0.04,
      );
      gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 0.55);
      osc.start();
      osc.stop(context.currentTime + 0.6);
      const ctx = context;
      osc.onended = () => void ctx.close();
      setSpeakerTested(true);
    } catch {
      if (context && context.state !== "closed") void context.close();
      setHeard(false);
      setError(
        "El navegador ha bloquejat la sortida d’àudio. Activa el so d’aquesta pestanya i torna a prémer «Provar altaveu».",
      );
    }
  }
  async function start() {
    if (starting.current || active || startGate.current.pending ||
        guidePending.current || guideRestore.current) return;
    starting.current = true;
    setCancelling(false);
    setBusy(true);
    setError("");
    setOutputSeen(false);
    setTranscript([]);
    setState(null);
    stopDiagnostic();
    try {
      const started = await startGate.current.run(
        () => api<SessionToken>("/sessions", { scenario }),
        (session) => {
          hasSession.current = true;
          expectedSession.current = session.id;
          setState(null);
          setRefresh((n) => n + 1);
          conversation.setMuted(false);
          conversation.startSession({
            conversationToken: session.conversation_token,
            connectionType: "webrtc",
          });
          timeout.current = setTimeout(() => {
            conversation.endSession();
            starting.current = false;
            setBusy(false);
            setError(
              "La connexió ha trigat massa. Tanca la sessió i torna-ho a provar.",
            );
            void endBackend();
          }, 30000);
        },
        async () => {
          // The late response owns the cookie's session; no newer mint can race this cleanup.
          hasSession.current = true;
          await endBackend();
        },
      );
      if (!started) {
        starting.current = false;
        setBusy(false);
      }
    } catch (e) {
      starting.current = false;
      setBusy(false);
      setError(displayError(e));
      void endBackend();
    }
  }
  async function end() {
    startGate.current.cancel();
    if (startGate.current.pending) {
      setCancelling(true);
      setAudioHint("Cancel·lant la connexió pendent…");
      return;
    }
    if (timeout.current) clearTimeout(timeout.current);
    conversation.endSession();
    starting.current = false;
    setBusy(false);
    await endBackend();
  }
  async function unlock(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/access", { code });
      setCode("");
      await loadConfig();
    } catch (e) {
      setError(displayError(e));
    } finally {
      setBusy(false);
    }
  }
  async function retry() {
    setRetrying(true);
    setError("");
    try {
      await api("/session/retry", null);
      setRefresh((n) => n + 1);
    } catch (e) {
      setError(displayError(e));
    } finally {
      setRetrying(false);
    }
  }
  async function updateGuide(path: "/guided" | "/guided/action", body: object) {
    if (guidePending.current) return;
    guideRestore.current?.abort();
    guidePending.current = true;
    setGuideBusy(true);
    setError("");
    try {
      const snapshot = await api<GuidedState>(path, body);
      window.history.replaceState(null, "", "#guided");
      setGuided(snapshot);
    } catch (e) {
      if (e instanceof ApiError && (e.code === "session_required" || e.code === "access_required")) {
        exitGuide();
        await loadConfig();
      }
      setError(displayError(e));
    } finally {
      guidePending.current = false;
      setGuideBusy(false);
    }
  }
  function startGuide(scenario: GuidedScenario) {
    if (!guided && (active || starting.current || hasSession.current)) return;
    stopDiagnostic();
    void updateGuide("/guided", { scenario, restart_from: guided?.view.session.id });
  }
  function guideAction(action: GuidedAction) {
    if (guided) void updateGuide("/guided/action", { id: guided.view.session.id, action });
  }
  function exitGuide() {
    guideRestore.current?.abort();
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    setGuided(null);
    setError("");
    requestAnimationFrame(() => guideEntry.current?.focus());
  }
  const state = guided?.view ?? liveState;
  const view = currentView(state, now);
  const status = connecting
    ? cancelling
      ? "Cancel·lant…"
      : "Connectant…"
    : connected
      ? conversation.isMuted
        ? "Micro silenciat"
        : conversation.isSpeaking
          ? "L’Ona parla"
          : "L’Ona t’escolta"
      : "Coneix l’Ona";
  const checkedProduct = view.checked
    ? view.products.find((p) =>
        p.variants.some((v) => v.sku === view.checked?.sku),
      )
    : null;
  const checkedVariant = checkedProduct?.variants.find(
    (v) => v.sku === view.checked?.sku,
  );
  const colours: Record<string, string> = {
    ivori: "#e4dfd0",
    blau: "#677b95",
    negre: "#383a38",
    verd: "#889280",
    sorra: "#c5b49c",
    terracota: "#b66d51",
    blanc: "#f8f6ee",
    crema: "#e8e0ca",
    navy: "#3b4559",
    olive: "#8a8e71",
    sand: "#c5b49c",
    ivory: "#e4dfd0",
    black: "#383a38",
    blue: "#677b95",
    white: "#f8f6ee",
    sage: "#889280",
    terracotta: "#b66d51",
  };
  return localizeTree(
    <div className="site-shell">
      <header className="masthead">
        <a href="/" className="brand" aria-label="Fil inici">
          fil
          <span className="brand-thread" aria-hidden="true">
            ⌁
          </span>
        </a>
        <span className="masthead-note">
          PECES AMB CALMA.
          <br />
          CONVERSES AMB SENTIT.
        </span>
        <div className="header-right">
          <label
            className="locale-control"
            title="La llengua de la web no canvia la veu de la conversa."
          >
            <span className="sr-only">Idioma de la interfície</span>
            <select
              aria-label="Idioma de la interfície"
              value={locale}
              onChange={(e) => setLocale(e.target.value as Locale)}
            >
              <option value="en">English</option>
              <option value="ca">Català</option>
              <option value="es">Español</option>
            </select>
          </label>
          <span className="demo-tag">BOTIGA FICTÍCIA · DEMOSTRACIÓ</span>
          <button
            className="operator-toggle"
            onClick={() => setOperatorOpen(!operatorOpen)}
            aria-expanded={operatorOpen}
            aria-controls="operator"
          >
            {operatorOpen ? "Tancar" : "Veure"} les accions{" "}
            <span aria-hidden="true">↗</span>
          </button>
        </div>
      </header>
      <main>
        {!guided && <section className="intro">
          <div className="intro-main">
            <p className="eyebrow">EL TEU ESTIL COMENÇA AMB UNA CONVERSA</p>
            <h1>
              Troba allò
              <br />
              que va <em>amb tu.</em>
            </h1>
            <p className="intro-copy">
              Un casament, un color, una idea a mig fer.
              <br />
              Explica-ho a l’Ona. En trobarem el fil.
            </p>
            {config && !gate && (
              <div className="intro-actions">
                <button
                  className="primary"
                  ref={guideEntry}
                  onClick={() => startGuide("normal")}
                  disabled={guideBusy || guideRestoring || active || liveState?.session?.status === "active"}
                >
                  Provar la demostració guiada
                </button>
                {config.configured && <a className="text-button" href="#voice">Anar a la veu en directe</a>}
              </div>
            )}
          </div>
          <div className="intro-aside">
            <svg
              viewBox="0 0 280 210"
              role="img"
              aria-label="Un fil dibuixa un llaç"
            >
              <path
                d="M-10 155C90 180 60 20 160 45S215 200 130 155S125 20 230 85S230 190 300 140"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              />
              <path
                d="M130 155c-30-35 20-80 40-60s-25 48-40 60"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              />
            </svg>
            <p>
              Menys buscar.
              <br />
              <em>Més trobar-te.</em>
            </p>
          </div>
        </section>}
        {error && (
          <div className="notice" role="alert">
            <span>{error}</span>
            <button className="text-button" onClick={() => setError("")}>
              Tancar ×
            </button>
          </div>
        )}
        {!config && (
          <div className="loading">
            Preparant la botiga…{" "}
            <button className="text-button" onClick={loadConfig}>
              Tornar a carregar
            </button>
          </div>
        )}
        {gate && (
          <form className="gate" onSubmit={unlock}>
            <div>
              <p className="eyebrow">UNA INVITACIÓ A PROVAR-HO</p>
              <h2>Benvingut a Fil.</h2>
              <p>Introdueix el codi d’accés a la demostració.</p>
            </div>
            <label>
              Codi d’accés
              <input
                type="password"
                autoComplete="off"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                required
              />
            </label>
            <button className="primary" disabled={busy}>
              Entrar <Icon name="arrow" />
            </button>
          </form>
        )}
        {config && !gate && (
          <>
            <div className="shop-layout">
              {guided ? (
                <GuidedPanel
                  guide={guided}
                  quote={view.quote}
                  expired={view.expired}
                  busy={guideBusy}
                  locale={locale}
                  onAction={guideAction}
                  onStart={startGuide}
                  onExit={exitGuide}
                />
              ) : (
              <aside id="voice" className="voice-panel" aria-label="Conversa amb l’Ona">
                <div className="panel-heading">
                  <span className="eyebrow">LA TEVA ASSISTENT</span>
                  <span className="language">EN / CA / ES</span>
                </div>
                <div
                  className={"voice-emblem " + (connected ? "live" : "")}
                  aria-hidden="true"
                >
                  <div className="voice-core">
                    <span />
                    <span />
                    <span />
                    <span />
                    <span />
                  </div>
                  <span className="voice-orbit" />
                </div>
                <h2 aria-live="polite">{status}</h2>
                <p className="voice-description">
                  {connected
                    ? "Parla, interromp, canvia d’idea. L’Ona segueix el teu ritme."
                    : "Una assistent d’IA que t’ajuda a triar. Sense compte, sense presses."}
                </p>
                <div className="call-controls">
                  {!active ? (
                    <button
                      className="primary"
                      onClick={start}
                      disabled={
                        !config.configured ||
                        guideBusy ||
                        guideRestoring ||
                        !micReady ||
                        !heard ||
                        state?.session?.status === "active"
                      }
                    >
                      <Icon name="mic" /> Parlar amb l’Ona <Icon name="arrow" />
                    </button>
                  ) : (
                    <>
                      <button
                        className="secondary"
                        disabled={!connected}
                        onClick={() =>
                          conversation.setMuted(!conversation.isMuted)
                        }
                        aria-pressed={conversation.isMuted}
                      >
                        {conversation.isMuted ? "Activar micro" : "Silenciar"}
                      </button>
                      <button className="end-button" onClick={end}>
                        Acabar
                      </button>
                    </>
                  )}
                </div>
                {!active && state?.session?.status === "active" && (
                  <button className="text-button" onClick={end}>
                    Tancar la sessió anterior
                  </button>
                )}
                {!config.configured && (
                  <p className="small-note">
                    El servei de veu encara no està configurat.
                  </p>
                )}
                {active && (
                  <div className="live-audio">
                    <Meter value={input} label="Micro" />
                    <Meter value={output} label="Veu" />
                    <p>
                      {outputSeen
                        ? "Senyal d’àudio rebut"
                        : "Esperant senyal d’àudio"}
                    </p>
                  </div>
                )}
                {connected && (
                  <p className="audio-hint" role="status">
                    {audioHint}
                  </p>
                )}
                <div className="preflight">
                  <div className="section-label">
                    <h3>Un moment per al so</h3>
                    <span>01 / 02</span>
                  </div>
                  <button
                    className={"check-button " + (micReady ? "checked" : "")}
                    onClick={micPending ? stopDiagnostic : testMic}
                    disabled={active}
                  >
                    <Icon name={micReady ? "check" : "mic"} />
                    <span>
                      {micPending
                        ? "Esperant permís · cancel·lar"
                        : micTesting
                          ? "Digues alguna cosa…"
                          : micReady
                            ? "Micròfon autoritzat"
                            : "Provar micròfon"}
                      <small>
                        {micReady ? device : "Permet l’accés al navegador"}
                      </small>
                    </span>
                  </button>
                  {micTesting && (
                    <Meter value={input} label="Nivell d’entrada" />
                  )}
                  <button
                    className={"check-button " + (heard ? "checked" : "")}
                    onClick={testSpeaker}
                    disabled={volume === 0}
                  >
                    <Icon name={heard ? "check" : "speaker"} />
                    <span>
                      Provar altaveu<small>Escolta un to breu</small>
                    </span>
                  </button>
                  {speakerTested && (
                    <label className="heard">
                      <input
                        type="checkbox"
                        checked={heard}
                        onChange={(e) => setHeard(e.target.checked)}
                      />
                      He sentit el to
                    </label>
                  )}
                  <label className="volume-label">
                    <Icon name="speaker" />
                    <span>Volum</span>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={volume}
                      onChange={(e) => setVolume(Number(e.target.value))}
                    />
                    <span>{Math.round(volume * 100)}%</span>
                  </label>
                </div>
                <details className="scenario-area">
                  <summary>Opcions de demostració</summary>
                  <label htmlFor="scenario">Situació</label>
                  <select
                    id="scenario"
                    value={scenario}
                    onChange={(e) => setScenario(e.target.value)}
                    disabled={active || state?.session?.status === "active"}
                  >
                    {config.scenarios.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                  <p>
                    El catàleg, l’estoc i els enviaments són sintètics. No hi ha
                    compres ni cobrament.
                  </p>
                </details>
              </aside>
              )}
              <div className="selection-panel">
                <div className="selection-heading">
                  <div>
                    <p className="eyebrow">
                      TRIAT A PARTIR DEL QUE ENS EXPLIQUES
                    </p>
                    <h2>
                      La teva selecció<span>.</span>
                    </h2>
                  </div>
                  <span className="selection-count">
                    {view.products.length
                      ? String(view.products.length).padStart(2, "0")
                      : "—"}{" "}
                    peces
                  </span>
                </div>
                {pollError && !guided && (
                  <div className="inline-error" role="status">
                    {pollError} No podem confirmar la selecció actual.
                  </div>
                )}
                {view.expired && !guided && (
                  <div className="inline-error" role="status">
                    La sessió ha caducat. Comença una conversa nova per
                    consultar l’estoc actual.
                  </div>
                )}
                {state?.error && !guided && (
                  <div className="inline-error" role="status">
                    La consulta no s’ha completat. L’Ona pot ajudar-te a
                    tornar-ho a provar; no mostrem disponibilitat anterior.
                  </div>
                )}
                {view.products.length > 0 ? (
                  <>
                    <div className="criteria">
                      <span>SELECCIÓ ACTUAL</span>
                      {state?.criteria?.size && (
                        <span>Talla {state.criteria.size}</span>
                      )}
                      {state?.criteria?.colour && (
                        <span>{state.criteria.colour}</span>
                      )}
                      {state?.criteria?.max_price_cents != null && (
                        <span>
                          Fins a {euro(state.criteria.max_price_cents)} / peça
                        </span>
                      )}
                    </div>
                    <div className="product-grid">
                      {view.products.map((product, index) => (
                        <article className="product-card" key={product.id}>
                          <div className="product-image">
                            <span className="product-number">0{index + 1}</span>
                            {productImage(product.image_path) && (
                              <img
                                src={productImage(product.image_path)}
                                alt={"Il·lustració neutra de " + product.name}
                                loading="lazy"
                              />
                            )}
                            <span className="illustration-label">
                              IL·LUSTRACIÓ · COLOR ORIENTATIU
                            </span>
                          </div>
                          <div className="product-title">
                            <h3>{product.name}</h3>
                            <span>{euro(product.price_cents)}</span>
                          </div>
                          <p className="product-description">
                            {product.description}
                          </p>
                          <div className="swatches">
                            {[
                              ...new Set(product.variants.map((v) => v.colour)),
                            ].map((colour) => (
                              <span key={colour} className="swatch-label">
                                <i
                                  style={{
                                    backgroundColor:
                                      colours[colour.toLowerCase()] ??
                                      "#c9c6bc",
                                  }}
                                  aria-hidden="true"
                                />
                                {colour}
                              </span>
                            ))}
                          </div>
                          <div className="variants">
                            {product.variants.map((variant) => (
                              <span
                                key={variant.sku}
                                className={
                                  variant.available_quantity !== null &&
                                  variant.available_quantity > 0
                                    ? "available"
                                    : "unavailable"
                                }
                                title={
                                  variant.colour +
                                  " · " +
                                  (variant.available_quantity !== null &&
                                  variant.available_quantity > 0
                                    ? variant.available_quantity +
                                      " disponibles"
                                    : variant.available_quantity === null
                                      ? "Estoc no confirmat"
                                      : "Sense estoc")
                                }
                              >
                                {variant.colour} / {variant.size}
                                {variant.available_quantity === null
                                  ? " — no confirmat"
                                  : variant.available_quantity === 0
                                    ? " — esgotat"
                                    : ""}
                              </span>
                            ))}
                          </div>
                          <details className="fit-notes">
                            <summary>Com és i com queda</summary>
                            <p>{product.fit_notes}</p>
                            <dl>
                              {Object.entries(product.garment_measurements).map(
                                ([size, m]) => (
                                  <div key={size}>
                                    <dt>{size}</dt>
                                    <dd>
                                      Pit {m.chest_cm} cm · llarg {m.length_cm}{" "}
                                      cm
                                    </dd>
                                  </div>
                                ),
                              )}
                            </dl>
                            <small>
                              Mesures de la peça, no una garantia de talla.
                            </small>
                          </details>
                        </article>
                      ))}
                    </div>
                    <p className="selection-footnote">
                      Estoc segons l’última consulta. Preu per peça. Enviament a
                      part. Demana a l’Ona que comprovi la talla i el color
                      exactes.
                    </p>
                  </>
                ) : (
                  <div className="empty-selection">
                    <div className="empty-illustration" aria-hidden="true">
                      <svg viewBox="0 0 180 150">
                        <path
                          d="M85 41c-17-16 18-31 18-11 0 11-13 11-13 21l64 40c7 5 3 12-5 12H31c-8 0-12-7-5-12l64-40"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.5"
                        />
                        <path
                          d="M55 115h70M70 126h40"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1"
                        />
                      </svg>
                    </div>
                    <h3>
                      {state?.criteria && !state.error
                        ? "Encara no hem trobat la peça."
                        : "Comencem per una idea."}
                    </h3>
                    <p>
                      {state?.criteria && !state.error
                        ? "No hi ha coincidències amb aquests criteris. Pots parlar amb l’Ona abans de canviar-los."
                        : "Les peces apareixeran aquí quan l’Ona consulti el catàleg per a tu."}
                    </p>
                    <blockquote>
                      “Tinc un casament, però no vull anar <br />
                      massa formal. Què em recomanes?”
                    </blockquote>
                    <span className="empty-detail">
                      CAP PEÇA SELECCIONADA ENCARA
                    </span>
                  </div>
                )}
                {view.checked && (
                  <section className="delivery-panel">
                    <div>
                      <p className="eyebrow">UNA COMPROVACIÓ CONCRETA</p>
                      <h3>{checkedProduct?.name ?? "Variant consultada"}</h3>
                      <p>
                        {checkedVariant
                          ? checkedVariant.colour +
                            " · talla " +
                            checkedVariant.size
                          : view.checked.sku}
                      </p>
                    </div>
                    <div className="delivery-details">
                      <strong>
                        {availabilityLabel(view.checked.available_quantity)}
                      </strong>
                      {view.quote ? (
                        <>
                          <span>
                            Arribada estimada:{" "}
                            {view.checked.estimated_arrival_date
                              ? date(view.checked.estimated_arrival_date)
                              : "No confirmada"}
                          </span>
                          <span>
                            Enviament: {euro(view.quote.shipping_cents)}
                          </span>
                          <span>
                            {view.quote.destination} ·{" "}
                            {view.quote.delivery_method === "express"
                              ? "Exprés"
                              : "Estàndard"}
                          </span>
                          <span>
                            Peça: {euro(view.quote.item_price_cents)} · total
                            amb enviament:{" "}
                            {euro(
                              view.quote.item_price_cents +
                                view.quote.shipping_cents,
                            )}
                          </span>
                          <small>
                            Estimació sintètica · vàlida{" "}
                            {remaining(view.quote.expires_at, now)}
                          </small>
                        </>
                      ) : (
                        <span>
                          No hi ha cap proposta de reserva vigent. Consulta amb
                          l’Ona la destinació i la data.
                        </span>
                      )}
                    </div>
                  </section>
                )}
                {state?.reservation && (
                  <ReservationCard
                    locale={locale}
                    reservation={state.reservation}
                    active={!!view.reservation}
                    now={now}
                  />
                )}
                {!guided && <section className="transcript">
                  <div className="section-label">
                    <h3>El fil de la conversa</h3>
                    <span>ONA + TU</span>
                  </div>
                  <div
                    className="transcript-scroll"
                    role="log"
                    aria-label="Transcripció de la conversa"
                    aria-live="polite"
                  >
                    {!transcript.length ? (
                      <p className="empty-transcript">
                        Aquí quedarà el que us aneu dient.
                      </p>
                    ) : (
                      transcript.map((line) => (
                        <div
                          className={"transcript-line " + line.role}
                          key={line.id}
                        >
                          <span>{line.role === "user" ? "TU" : "ONA"}</span>
                          <p data-untranslated>{line.message}</p>
                        </div>
                      ))
                    )}
                    <div ref={transcriptEnd} />
                  </div>
                </section>}
              </div>
            </div>
            <section
              id="operator"
              className="operator-drawer"
              hidden={!operatorOpen}
            >
              <div className="section-label">
                <div>
                  <p className="eyebrow">VISTA DE L’OPERADOR</p>
                  <h2>Allò que ha passat, de debò.</h2>
                </div>
                <button
                  className="text-button"
                  onClick={() => setOperatorOpen(false)}
                >
                  Tancar ×
                </button>
              </div>
              <p className="small-note">
                Resultats reals dels serveis de demostració. Historial separat
                de la selecció actual; sense raonament intern ni credencials.
              </p>
              <div className="operator-content">
                <ol className="timeline">
                  {!state?.events.length ? (
                    <li className="small-note">Encara no hi ha accions.</li>
                  ) : (
                    state.events.map((event) => (
                      <li key={event.sequence}>
                        <span
                          className={
                            "event-dot " + (event.status >= 400 ? "failed" : "")
                          }
                        />
                        <div>
                          <strong>
                            {eventLabels[event.kind] ?? "Acció del servei"}
                          </strong>
                          <small>
                            {event.status >= 400
                              ? "No completada"
                              : "Completada"}{" "}
                            · HTTP {event.status} · #{event.sequence}
                          </small>
                        </div>
                        <time>{clock(event.at)}</time>
                      </li>
                    ))
                  )}
                </ol>
                <div className="operator-reservation">
                  <p className="eyebrow">RESERVA OBSERVADA</p>
                  {state?.reservation ? (
                    <>
                      <code>{state.reservation.id}</code>
                      <p>
                        {view.reservation
                          ? "Retenció activa"
                          : "Retenció caducada"}
                      </p>
                      <button
                        className="secondary"
                        disabled={
                          retrying || guideBusy ||
                          !view.reservation ||
                          state.session?.status !== "active"
                        }
                        onClick={guided ? () => guideAction("retry") : retry}
                      >
                        {retrying || guideBusy
                          ? "Repetint…"
                          : "Provar reintent de la reserva"}
                      </button>
                      {view.lastRetry && (
                        <p className="retry-result">
                          {view.lastRetry.created
                            ? "Nova reserva retornada"
                            : "Mateixa reserva · created: false"}
                          <br />
                          <code>{view.lastRetry.reservation.id}</code>
                        </p>
                      )}
                    </>
                  ) : (
                    <p className="small-note">
                      El reintent només apareix després d’una reserva existent.
                      Mai en crea la primera.
                    </p>
                  )}
                </div>
              </div>
            </section>
          </>
        )}
      </main>
      <footer>
        <span className="footer-brand">fil⌁</span>
        <span>Roba fictícia. Converses amb sentit.</span>
        <span>Una demostració de Jordi Catafal ↗</span>
      </footer>
    </div>,
    locale,
  );
}
