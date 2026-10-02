import { useEffect, useMemo, useRef, useState } from "react";
import Icon from "../components/Icon.jsx";
import Logo from "../components/Logo.jsx";
import CopyAnswerButton from "../components/CopyAnswerButton.jsx";
import LanguageSwitcher from "../components/LanguageSwitcher.jsx";
import ThemeToggle from "../components/ThemeToggle.jsx";
import { useLanguage } from "../i18n/LanguageContext.jsx";
import { useTheme } from "../theme/ThemeContext.jsx";
import { createConversation, deleteConversation, getConversationMessages, listConversations, sendChatMessage } from "../services/api.js";
import { deleteDocument, DOCUMENT_ACCEPT, listDocuments, uploadDocument, validateDocument } from "../services/documents.js";
import { createSpeechRecognizer } from "../services/speech.js";
import { sendRecognizedTranscript } from "../services/voiceFlow.js";
import Documents from "./Documents.jsx";
import Voice from "./Voice.jsx";
import Settings from "./Settings.jsx";

const PIN_STORAGE_KEY = "apna-wakeel:pinned-conversations";

function createId() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function getChatErrorKey(error) {
  if (error?.status === 429 || /rate.?limit|usage limit|quota|tokens per (day|minute)/i.test(error?.message || "")) return "chat.aiRateLimited";
  if (error?.status === 504) return "chat.aiTimeout";
  if (error?.status === 503 && /database/i.test(error?.message || "")) return "chat.dataUnavailable";
  if (error?.message === "chat_not_connected") return "chat.notConnected";
  if (error?.message === "chat_invalid_response") return "chat.invalidResponse";
  if (/legal analysis service/i.test(error?.message || "")) return "chat.aiUnavailable";
  if (/database|storage/i.test(error?.message || "")) return "chat.dataUnavailable";
  if (/AI service/i.test(error?.message || "")) return "chat.aiUnavailable";
  return "chat.sendError";
}

function isOfficialLawUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && [
      "pakistancode.gov.pk",
      "www.pakistancode.gov.pk",
      "kpcode.kp.gov.pk",
      "www.kpcode.kp.gov.pk",
    ].includes(url.hostname.toLowerCase());
  } catch {
    return false;
  }
}

function ChatMessageContent({ content }) {
  const parts = String(content || "").split(/(https:\/\/[^\s]+)/g);
  return (
    <p>
      {parts.map((part, index) => isOfficialLawUrl(part)
        ? <a key={index} href={part} target="_blank" rel="noreferrer">{part}</a>
        : part)}
    </p>
  );
}

function ConversationPanel({ conversation, conversationMissing, sending, error, operationError, documents, selectedAttachments, onSelectFiles, onRemoveAttachment, onSend, onRetry, onNewChat, onVoiceConversation }) {
  const { t, language } = useLanguage();
  const [draft, setDraft] = useState("");
  const [attachmentError, setAttachmentError] = useState("");
  const [voiceState, setVoiceState] = useState("idle");
  const [dictationText, setDictationText] = useState("");
  const bottomRef = useRef(null);
  const attachmentInputRef = useRef(null);
  const recognizerRef = useRef(null);
  const dictationSessionRef = useRef(null);
  const languageRef = useRef(language);
  languageRef.current = language;
  const attachedDocuments = selectedAttachments.map((id) => documents.find((item) => item.localId === id)).filter(Boolean);
  const attachmentsReady = attachedDocuments.every((document) => document.backendId);

  useEffect(() => () => {
    dictationSessionRef.current?.recognizer.cancel();
    dictationSessionRef.current = null;
  }, []);

  function startDictation() {
    if (["listening", "processing", "sending"].includes(voiceState)) return;
    const speechLanguage = language;
    const recognizer = createSpeechRecognizer(speechLanguage);
    if (!recognizer.supported) {
      setVoiceState("unsupported");
      return;
    }
    const session = { recognizer, language: speechLanguage, finalReceived: false, failed: false, cancelled: false };
    dictationSessionRef.current = session;
    recognizerRef.current = recognizer;
    setDictationText("");
    setVoiceState("listening");
    recognizer.start({
      onInterim: (text) => {
        if (dictationSessionRef.current === session && !session.cancelled) setDictationText(text);
      },
      onFinal: (text) => {
        if (dictationSessionRef.current !== session || session.cancelled || session.finalReceived) return;
        session.finalReceived = true;
        const finalText = String(text || "").trim();
        if (!finalText) {
          setVoiceState("empty");
          return;
        }
        if (languageRef.current !== session.language) {
          setVoiceState("languageChanged");
          return;
        }
        setDictationText(finalText);
        setVoiceState("sending");
        Promise.resolve(sendRecognizedTranscript(
          finalText,
          session.language,
          (content, selectedLanguage) => onSend(content, "", selectedLanguage),
        )).then((result) => {
          if (dictationSessionRef.current !== session) return;
          if (result?.success) {
            setDictationText("");
            setVoiceState("idle");
          } else {
            setDraft(finalText);
            setVoiceState("error");
          }
        }).catch(() => {
          if (dictationSessionRef.current !== session) return;
          setDraft(finalText);
          setVoiceState("error");
        });
      },
      onError: (error) => {
        if (dictationSessionRef.current !== session || session.cancelled) return;
        session.failed = true;
        if (error.type === "permission-denied") setVoiceState("permission");
        else if (error.type === "unsupported") setVoiceState("unsupported");
        else if (error.type === "no-speech") setVoiceState("empty");
        else if (error.type === "audio-capture") setVoiceState("audioCapture");
        else setVoiceState("error");
      },
      onEnd: () => {
        if (dictationSessionRef.current !== session || session.cancelled) return;
        if (!session.finalReceived && !session.failed) setVoiceState("empty");
      },
    });
  }

  function stopDictation() {
    recognizerRef.current?.stop();
    setVoiceState("processing");
  }

  function cancelDictation() {
    const session = dictationSessionRef.current;
    if (session) {
      session.cancelled = true;
      session.recognizer.cancel();
    }
    dictationSessionRef.current = null;
    setDictationText("");
    setVoiceState("idle");
  }

  async function submit(event) {
    event.preventDefault();
    const content = draft.trim();
    if ((!content && attachedDocuments.length === 0) || sending || conversationMissing || !attachmentsReady) return;
    const message = content || (attachedDocuments.length > 0 ? t("documents.chatPrompt") : "");
    const sent = await onSend(message);
    if (sent) setDraft("");
  }

  async function selectFiles(files) {
    setAttachmentError("");
    const results = await onSelectFiles(files);
    const failed = results?.find((result) => result?.errorKey);
    if (failed) setAttachmentError(failed.errorKey);
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  const messages = conversation?.messages || [];

  useEffect(() => {
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    bottomRef.current?.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "end" });
  }, [messages.length, sending, error]);

  return (
    <section className="conversation-panel" aria-label={t("chat.title")}>
      <div className="conversation-scroll" role="log" aria-live="polite" aria-relevant="additions text">
        {conversationMissing ? (
          <div className="chat-empty chat-missing">
            <span className="icon-badge" aria-hidden="true"><Icon name="message" size={22} /></span>
            <h2>{t("chat.historyUnavailable")}</h2>
            <p>{t("chat.historyUnavailableText")}</p>
            <button className="app-button app-button-primary" type="button" onClick={onNewChat}>
              <Icon name="plus" size={18} />{t("chat.newChat")}
            </button>
          </div>
        ) : messages.length === 0 ? (
          <div className="chat-empty">
            <span className="chat-mark" aria-hidden="true"><Logo size={64} /></span>
            <p className="app-eyebrow">{t("chat.eyebrow")}</p>
            <h2>{t("chat.emptyTitle")}</h2>
            <p>{t("chat.emptyText")}</p>
          </div>
        ) : (
          <div className="message-list">
            {messages.map((message) => (
              <article className={`chat-message chat-message-${message.role}`} key={message.id}>
                <span className="message-label">{message.role === "user" ? t("chat.you") : t("chat.assistant")}</span>
                <ChatMessageContent content={message.content} />
                {message.role === "assistant" && <CopyAnswerButton content={message.content} />}
                {message.attachments?.length > 0 && (
                  <ul className="message-attachments" aria-label={t("documents.attachments")}>
                    {message.attachments.map((attachment) => <li key={attachment.id}><Icon name="file" size={16} /><span>{attachment.name}</span></li>)}
                  </ul>
                )}
                {message.createdAt && (
                  <time dateTime={message.createdAt}>
                    {new Intl.DateTimeFormat(language === "ur" ? "ur-PK" : "en-PK", {
                      hour: "numeric",
                      minute: "2-digit",
                    }).format(new Date(message.createdAt))}
                  </time>
                )}
              </article>
            ))}
            {sending && (
              <div className="chat-pending" role="status">
                <span className="chat-pending-dot" aria-hidden="true" />
                <span>{t("chat.waiting")}</span>
              </div>
            )}
          </div>
        )}
        <div ref={bottomRef} aria-hidden="true" />
      </div>

      {!conversationMissing && (
        <div className="chat-compose-wrap">
          {(error || operationError) && (
            <div className="chat-error" role="alert">
              <p>{t(operationError || getChatErrorKey(error))}</p>
              {error && <button className="app-button app-button-quiet" type="button" disabled={sending} onClick={onRetry}>
                <Icon name="restart" size={16} />{t("chat.retry")}
              </button>}
            </div>
          )}
          {attachedDocuments.length > 0 && (
            <ul className="chat-attachment-list" aria-label={t("documents.attachments")}>
              {attachedDocuments.map((document) => (
                <li className={`chat-attachment chat-attachment-${document.status}`} key={document.localId}>
                  <Icon name="file" size={17} />
                  <span><strong>{document.name}</strong><small>{t(`documents.status.${document.status}`)}</small>{document.errorKey && <small className="document-error">{t(document.errorKey)}</small>}</span>
                  <button className="app-icon-button" type="button" aria-label={`${t("documents.removeAttachment")}: ${document.name}`} title={t("documents.removeAttachment")} onClick={() => onRemoveAttachment(document.localId)}><Icon name="close" size={16} /></button>
                </li>
              ))}
            </ul>
          )}
          {voiceState !== "idle" && (
            <div className="chat-voice-status" role={["permission", "audioCapture", "error"].includes(voiceState) ? "alert" : "status"} aria-live="polite">
              <span>{voiceState === "listening" ? `${t("chat.voiceListening")} ${dictationText}` : voiceState === "processing" ? t("chat.voiceProcessing") : voiceState === "sending" ? t("chat.voiceSending") : voiceState === "unsupported" ? t("chat.voiceInputUnavailable") : voiceState === "permission" ? t("chat.voicePermission") : voiceState === "empty" ? t("chat.voiceNoSpeech") : voiceState === "audioCapture" ? t("chat.voiceAudioCapture") : voiceState === "languageChanged" ? t("chat.voiceLanguageChanged") : t("chat.voiceUnavailable")}</span>
              {voiceState === "listening" && <div className="chat-voice-actions"><button className="app-button app-button-quiet" type="button" onClick={stopDictation}><Icon name="stop" size={15} />{t("voice.stop")}</button><button className="app-button app-button-quiet" type="button" onClick={cancelDictation}><Icon name="close" size={15} />{t("voice.cancel")}</button></div>}
              {voiceState === "processing" && <button className="app-button app-button-quiet" type="button" onClick={cancelDictation}><Icon name="close" size={15} />{t("voice.cancel")}</button>}
            </div>
          )}
          <form className="chat-compose" onSubmit={submit}>
            <input ref={attachmentInputRef} className="visually-hidden" type="file" accept={DOCUMENT_ACCEPT} multiple onChange={(event) => { selectFiles(Array.from(event.target.files || [])); event.target.value = ""; }} aria-label={t("documents.choose")} />
            <button className="chat-attach" type="button" aria-label={t("documents.choose")} title={t("documents.choose")} disabled={sending} onClick={() => attachmentInputRef.current?.click()}><Icon name="plus" size={19} /></button>
            <label className="visually-hidden" htmlFor="chat-message">{t("chat.inputLabel")}</label>
            <textarea
              id="chat-message"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={t("chat.placeholder")}
              rows={1}
              disabled={sending}
            />
            <button
              className="chat-mic"
              type="button"
              aria-label={voiceState === "listening" ? t("voice.stop") : t("chat.voiceInput")}
              title={voiceState === "listening" ? t("voice.stop") : t("chat.voiceInput")}
              onClick={() => (voiceState === "listening" ? stopDictation() : startDictation())}
              disabled={sending || ["processing", "sending"].includes(voiceState)}
            >
              <Icon name={voiceState === "listening" ? "stop" : "mic"} size={17} />
            </button>
            <button
              className="chat-voice"
              type="button"
              aria-label={t("chat.voiceConversation")}
              title={t("chat.voiceConversation")}
              onClick={onVoiceConversation}
              disabled={sending}
            >
              {t("chat.voiceConversation")}
            </button>
            <button
              className="chat-send"
              type="submit"
              aria-label={t("chat.send")}
              title={t("chat.send")}
              disabled={sending || ((!draft.trim() && attachedDocuments.length === 0) || !attachmentsReady)}
            >
              <Icon name="send" size={19} />
            </button>
          </form>
          {attachmentError && <p className="chat-attachment-error" role="alert">{t(attachmentError)}</p>}
          <p className="chat-disclaimer">{t("chat.footerNote")}</p>
        </div>
      )}
    </section>
  );
}

export default function Dashboard({ pathname, navigate, user, accessToken, onLogout, authError, onDismissAuthError }) {
  const { t, language } = useLanguage();
  const { theme } = useTheme();
  const [conversations, setConversations] = useState([]);
  const [sendingIds, setSendingIds] = useState(() => new Set());
  const [searchQuery, setSearchQuery] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [documents, setDocuments] = useState([]);
  const [documentsLoadError, setDocumentsLoadError] = useState("");
  const [selectedAttachments, setSelectedAttachments] = useState([]);
  const [activeConversationId, setActiveConversationId] = useState("");
  const [conversationStartError, setConversationStartError] = useState("");
  const [workspaceLoadError, setWorkspaceLoadError] = useState("");
  const [pinnedConversationIds, setPinnedConversationIds] = useState(() => {
    if (typeof window === "undefined") return {};
    try {
      return JSON.parse(window.localStorage.getItem(PIN_STORAGE_KEY) || "{}") || {};
    } catch {
      return {};
    }
  });
  const sidebarRef = useRef(null);
  const menuButtonRef = useRef(null);
  const drawerWasOpenRef = useRef(false);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(PIN_STORAGE_KEY, JSON.stringify(pinnedConversationIds));
    }
  }, [pinnedConversationIds]);

  useEffect(() => {
    if (!accessToken) {
      setConversations([]);
      return undefined;
    }

    let active = true;

    async function loadConversations() {
      try {
        const list = await listConversations({ accessToken });
        if (active) setWorkspaceLoadError("");
        const hydrated = await Promise.all(
          list.map(async (item) => {
            try {
              const messages = await getConversationMessages({ conversationId: item.id, accessToken });
              return {
                ...item,
                id: item.id,
                conversationId: item.id,
                title: item.title || t("chat.newChat"),
                messages: (messages || []).map((message) => ({
                  id: message.id,
                  role: message.role,
                  content: message.content,
                  createdAt: message.created_at || new Date().toISOString(),
                  attachments: [],
                })),
                error: null,
              };
            } catch (error) {
              if (active) setWorkspaceLoadError("chat.dataUnavailable");
              if (import.meta.env.DEV) console.error("Could not load conversation messages:", error);
              return {
                ...item,
                id: item.id,
                conversationId: item.id,
                title: item.title || t("chat.newChat"),
                messages: [],
                error: null,
              };
            }
          }),
        );

        if (active) setConversations(hydrated);
      } catch (error) {
        if (active) {
          setConversations([]);
          setWorkspaceLoadError("chat.dataUnavailable");
        }
        if (import.meta.env.DEV) console.error("Could not load conversations:", error);
      }
    }

    loadConversations();

    return () => {
      active = false;
    };
  }, [accessToken]);

  useEffect(() => {
    if (!accessToken) return;
    let active = true;
    listDocuments({ accessToken })
      .then((items) => {
        if (active) {
          setDocumentsLoadError("");
          setDocuments(items.map((item) => ({
            localId: item.id,
            backendId: item.id,
            name: item.name,
            type: item.type,
            size: item.size,
            status: "ready",
            progress: 100,
            file: null,
            errorKey: "",
          })));
        }
      })
      .catch((error) => {
        if (active) setDocumentsLoadError(error.message === "documents.backendUnsupported" ? error.message : "documents.loadError");
        if (import.meta.env.DEV) console.error("Could not load documents:", error);
      });
    return () => { active = false; };
  }, [accessToken]);

  const routeMatch = pathname.match(/^\/app\/chat\/([^/]+)$/);
  const routeId = routeMatch?.[1] && routeMatch[1] !== "new" ? decodeURIComponent(routeMatch[1]) : "";
  const conversation = conversations.find((item) => item.id === routeId);
  const conversationMissing = Boolean(routeId && !conversation);
  const isChatRoute = pathname.startsWith("/app/chat");
  const isDocumentsRoute = pathname === "/app/documents";
  const isVoiceRoute = pathname === "/app/voice";
  const isSettingsRoute = pathname === "/app/settings";
  const displayName = user?.user_metadata?.full_name || user?.email || t("chat.account");
  const activeConversation = conversations.find((item) => item.id === (routeId || activeConversationId)) || null;

  const sortedConversations = useMemo(() => {
    const normalized = searchQuery.trim().toLowerCase();
    const filtered = conversations.filter((item) => {
      if (!normalized) return true;
      const haystack = [item.title, ...item.messages.map((message) => message.content)].join(" ").toLowerCase();
      return haystack.includes(normalized);
    });

    const pinned = [];
    const recent = [];
    filtered.forEach((item) => {
      if (pinnedConversationIds[item.id]) pinned.push(item);
      else recent.push(item);
    });

    return { pinned, recent };
  }, [conversations, searchQuery, pinnedConversationIds]);

  const pinnedConversations = sortedConversations.pinned;
  const recentConversations = sortedConversations.recent;

  useEffect(() => {
    if (routeId && conversation) setActiveConversationId(routeId);
  }, [pathname, routeId, conversation]);

  useEffect(() => {
    if (mobileOpen) {
      sidebarRef.current?.querySelector("button")?.focus();
      const handleDrawerKeyDown = (event) => {
        if (event.key === "Escape") {
          setMobileOpen(false);
          return;
        }
        if (event.key !== "Tab") return;
        const controls = Array.from(sidebarRef.current?.querySelectorAll("button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled)") || []);
        if (!controls.length) return;
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      };
      document.addEventListener("keydown", handleDrawerKeyDown);
      drawerWasOpenRef.current = true;
      return () => document.removeEventListener("keydown", handleDrawerKeyDown);
    }
    if (drawerWasOpenRef.current) {
      menuButtonRef.current?.focus();
      drawerWasOpenRef.current = false;
    }
    return undefined;
  }, [mobileOpen]);

  function updateConversation(id, updater) {
    setConversations((current) => current.map((item) => (item.id === id ? updater(item) : item)));
  }

  async function removeConversation(item) {
    try {
      await deleteConversation({ conversationId: item.id, accessToken });
      setConversations((current) => current.filter((conversationItem) => conversationItem.id !== item.id));
      setPinnedConversationIds((current) => {
        const next = { ...current };
        delete next[item.id];
        return next;
      });
      if (activeConversationId === item.id || routeId === item.id) {
        setActiveConversationId("");
        navigate("/app/chat/new");
      }
    } catch (error) {
      if (import.meta.env.DEV) console.error("Could not delete conversation:", error);
      setWorkspaceLoadError(error.status === 401 ? "auth.session_restore_failed" : "chat.deleteError");
    }
  }

  function startNewChat() {
    setMobileOpen(false);
    setActiveConversationId("");
    setSelectedAttachments([]);
    navigate("/app/chat/new");
  }

  function openChat() {
    setMobileOpen(false);
    const target = activeConversation || conversations[0];
    navigate(target ? `/app/chat/${encodeURIComponent(target.id)}` : "/app/chat/new");
  }

  async function requestReply(id, messages, documentIds = [], messageLanguage = language) {
    if (sendingIds.has(id)) return;
    setSendingIds((current) => new Set(current).add(id));
    updateConversation(id, (item) => ({ ...item, error: null }));
    try {
      const currentConversation = conversations.find((item) => item.id === id);
      const result = await sendChatMessage({
        conversationId: currentConversation?.conversationId || id,
        messages,
        documentIds,
        language: messageLanguage,
        labels: {
          caseSummary: t("chat.caseSummary"),
          currentGuidance: t("chat.currentGuidance"),
          nextSteps: t("chat.nextSteps"),
          documentsNeeded: t("chat.documentsNeeded"),
          optionalDetails: t("chat.optionalDetails"),
          clarificationPrompt: t("chat.clarificationPrompt"),
          limitedNextStep: t("chat.limitedNextStep"),
          officialReferences: t("chat.officialReferences"),
          aiGenerated: t("chat.aiGenerated"),
          sourceVerified: t("chat.sourceVerified"),
          sourceRetrieved: t("chat.sourceRetrieved"),
          noOfficialEvidence: t("chat.noOfficialEvidence"),
          uncertainty: t("chat.uncertainty"),
          legalDisclaimer: t("chat.legalDisclaimer"),
          underReview: t("chat.underReview"),
          underReviewNotice: t("chat.underReviewNotice"),
          needDescription: t("chat.needDescription"),
          responseUnavailable: t("chat.responseUnavailable"),
        },
        newChatTitle: t("chat.newChat"),
        accessToken,
      });
      updateConversation(id, (item) => ({
        ...item,
        id: result.conversationId || item.id,
        conversationId: result.conversationId || item.conversationId || item.id,
        messages: [...item.messages, { ...result.message, id: createId(), createdAt: new Date().toISOString() }],
        error: null,
      }));
      return { success: true, response: result.message.content };
    } catch (error) {
      updateConversation(id, (item) => ({ ...item, error: { message: error.message, status: error.status } }));
      return false;
    } finally {
      setSendingIds((current) => {
        const next = new Set(current);
        next.delete(id);
        return next;
      });
    }
  }

  async function handleSend(content, requestedConversationId = "", messageLanguage = language) {
    setConversationStartError("");
    let target = requestedConversationId
      ? conversations.find((item) => item.id === requestedConversationId)
      : conversation;
    if (!target) {
      target = {
        id: createId(),
        title: content.slice(0, 48),
        messages: [],
        error: null,
        conversationId: "",
      };
    }

    if (!target.conversationId) {
      try {
        const created = await createConversation({
          title: target.title || t("chat.newChat"),
          accessToken,
        });
        target = {
          ...target,
          id: created.id,
          conversationId: created.id,
          title: created.title || target.title || t("chat.newChat"),
        };
      } catch (error) {
        if (import.meta.env.DEV) console.error("Could not create conversation:", error);
        setConversationStartError(/database|relation|table/i.test(error.message) ? "chat.dataUnavailable" : "chat.sendError");
        return false;
      }
    }

    if (sendingIds.has(target.id)) return false;
    const userMessage = { id: createId(), role: "user", content, createdAt: new Date().toISOString() };
    const messageAttachments = selectedAttachments
      .map((localId) => documents.find((item) => item.localId === localId))
      .filter((item) => item?.backendId)
      .map(({ backendId, name, type, size }) => ({ id: backendId, name, type, size }));
    userMessage.attachments = messageAttachments;
    const messages = [...target.messages, userMessage];
    const title = content.trim() || (messageAttachments.length ? messageAttachments[0].name : t("chat.newChat"));
    const updated = { ...target, title: target.messages.length === 0 ? title.slice(0, 48) : target.title, messages, error: null };
    setConversations((current) => [updated, ...current.filter((item) => item.id !== target.id)]);
    setActiveConversationId(target.id);
    setSelectedAttachments([]);
    if (!requestedConversationId && !conversation && pathname !== "/app/voice") navigate(`/app/chat/${encodeURIComponent(target.id)}`);
    return requestReply(target.id, messages, messageAttachments.map((item) => item.id), messageLanguage);
  }

  function retryLastMessage() {
    if (!conversation || sendingIds.has(conversation.id)) return;
    const lastUserMessage = [...conversation.messages].reverse().find((message) => message.role === "user");
    requestReply(conversation.id, conversation.messages, (lastUserMessage?.attachments || []).map((item) => item.id));
  }

  async function uploadFile(file, { attachToChat = false, retryId = "" } = {}) {
    const errorKey = validateDocument(file);
    if (errorKey) return { errorKey };
    const localId = retryId || createId();
    const initial = { localId, name: file.name, type: file.type, size: file.size, file, progress: 0, status: "uploading", errorKey: "" };
    setDocuments((current) => retryId
      ? current.map((item) => item.localId === retryId ? { ...initial, backendId: item.backendId } : item)
      : [initial, ...current]);
    if (attachToChat) setSelectedAttachments((current) => current.includes(localId) ? current : [...current, localId]);
    try {
      const uploaded = await uploadDocument(file, {
        accessToken,
        language,
        onProgress: (progress) => setDocuments((current) => current.map((item) => item.localId === localId ? { ...item, progress } : item)),
      });
      setDocuments((current) => current.map((item) => item.localId === localId
        ? { ...item, backendId: uploaded.id, name: uploaded.name, type: uploaded.type, size: uploaded.size, status: uploaded.status, progress: 100, file: null, errorKey: "" }
        : item));
      return { document: uploaded };
    } catch (error) {
      if (import.meta.env.DEV) console.error("Document upload failed:", error);
      const failureKey = error.message.startsWith("documents.") ? error.message : error.message === "api.endpointUnavailable" ? "documents.backendUnsupported" : error.message === "documents_not_connected" ? "documents.notConnected" : error.message === "documents_invalid_response" ? "documents.invalidResponse" : "documents.uploadError";
      setDocuments((current) => current.map((item) => item.localId === localId ? { ...item, status: "failed", errorKey: failureKey } : item));
      return { errorKey: failureKey };
    }
  }

  async function removeDocument(localId) {
    const document = documents.find((item) => item.localId === localId);
    if (document?.backendId) {
      try {
        await deleteDocument({ documentId: document.backendId, accessToken });
      } catch (error) {
        if (import.meta.env.DEV) console.error("Document delete failed:", error);
        return false;
      }
    }
    setDocuments((current) => current.filter((item) => item.localId !== localId));
    setSelectedAttachments((current) => current.filter((id) => id !== localId));
    return true;
  }

  function attachDocument(document) {
    if (!document.backendId) return;
    setSelectedAttachments((current) => current.includes(document.localId) ? current : [...current, document.localId]);
    setActiveConversationId("");
    setMobileOpen(false);
    navigate("/app/chat/new");
  }

  function openSection(path) {
    setMobileOpen(false);
    if (routeId && conversation) setActiveConversationId(routeId);
    navigate(path);
  }

  function handleVoiceSend(content, requestedConversationId = "", messageLanguage = language) {
    return handleSend(content, requestedConversationId || activeConversation?.id || "", messageLanguage);
  }

  function startVoiceConversation() {
    setActiveConversationId("");
    setSelectedAttachments([]);
    navigate("/app/voice");
  }

  function exitVoice() {
    navigate(activeConversation ? `/app/chat/${encodeURIComponent(activeConversation.id)}` : "/app/chat/new");
  }

  const currentSending = Boolean(activeConversation && sendingIds.has(activeConversation.id));
  const chatError = activeConversation?.error
    ? getChatErrorKey(activeConversation.error)
    : "";

  const navContent = (
    <>
      <button className="app-brand" type="button" onClick={() => { setMobileOpen(false); navigate("/app"); }}>
        <Logo size={42} />
        <span><strong>{t("brand")}</strong><small>{t("chat.workspace")}</small></span>
      </button>
      <button className="app-button app-button-primary app-new-chat" type="button" onClick={startNewChat}>
        <Icon name="plus" size={19} />{t("chat.newChat")}
      </button>
      <div className="app-search" aria-label={t("chat.searchLabel")}>
        <Icon name="search" size={15} />
        <input
          type="search"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          placeholder={t("chat.searchPlaceholder")}
          aria-label={t("chat.searchLabel")}
        />
      </div>
      <nav className="app-nav" aria-label={t("chat.navigation")}>
        <button type="button" className={`app-nav-link ${pathname === "/app" ? "active" : ""}`} aria-current={pathname === "/app" ? "page" : undefined} onClick={() => openSection("/app")}>
          <Icon name="dashboard" size={19} />{t("chat.dashboard")}
        </button>
        <button type="button" className={`app-nav-link ${isChatRoute ? "active" : ""}`} aria-current={isChatRoute ? "page" : undefined} onClick={openChat}>
          <Icon name="message" size={19} />{t("chat.chat")}
        </button>
        <button type="button" className={`app-nav-link ${isDocumentsRoute ? "active" : ""}`} aria-current={isDocumentsRoute ? "page" : undefined} onClick={() => openSection("/app/documents")}>
          <Icon name="file" size={19} />{t("nav.documents")}
        </button>
        <button type="button" className={`app-nav-link ${isSettingsRoute ? "active" : ""}`} aria-current={isSettingsRoute ? "page" : undefined} onClick={() => openSection("/app/settings")}>
          <Icon name="settings" size={19} />{t("nav.settings")}
        </button>
      </nav>
      <div className="app-history">
        {conversations.length === 0 ? (
          <p className="app-history-empty">{t("chat.noHistory")}</p>
        ) : (
          <>
            {pinnedConversations.length > 0 && (
              <div className="app-history-group">
                <h2>{t("chat.pinned")}</h2>
                <ul>
                  {pinnedConversations.map((item) => (
                    <li key={item.id} className="app-history-item">
                      <button type="button" className={`app-history-link ${item.id === routeId ? "active" : ""}`} aria-current={item.id === routeId ? "page" : undefined} title={item.title} onClick={() => { setMobileOpen(false); setActiveConversationId(item.id); navigate(`/app/chat/${encodeURIComponent(item.id)}`); }}>
                        <Icon name="message" size={16} />
                        <span>{item.title}</span>
                      </button>
                      <button type="button" className="app-history-pin" aria-label={t("chat.unpin")} title={t("chat.unpin")} onClick={(event) => { event.stopPropagation(); setPinnedConversationIds((current) => ({ ...current, [item.id]: false })); }}>
                        <Icon name="pin" size={13} />
                      </button>
                      <button type="button" className="app-history-pin" aria-label={`${t("chat.delete")}: ${item.title}`} title={t("chat.delete")} onClick={(event) => { event.stopPropagation(); removeConversation(item); }}>
                        <Icon name="close" size={13} />
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {recentConversations.length > 0 && (
              <div className="app-history-group">
                <h2>{t("chat.recent")}</h2>
                <ul>
                  {recentConversations.map((item) => (
                    <li key={item.id} className="app-history-item">
                      <button type="button" className={`app-history-link ${item.id === routeId ? "active" : ""}`} aria-current={item.id === routeId ? "page" : undefined} title={item.title} onClick={() => { setMobileOpen(false); setActiveConversationId(item.id); navigate(`/app/chat/${encodeURIComponent(item.id)}`); }}>
                        <Icon name="message" size={16} />
                        <span>{item.title}</span>
                      </button>
                      <button type="button" className="app-history-pin" aria-label={t("chat.pin")} title={t("chat.pin")} onClick={(event) => { event.stopPropagation(); setPinnedConversationIds((current) => ({ ...current, [item.id]: true })); }}>
                        <Icon name="pin" size={13} />
                      </button>
                      <button type="button" className="app-history-pin" aria-label={`${t("chat.delete")}: ${item.title}`} title={t("chat.delete")} onClick={(event) => { event.stopPropagation(); removeConversation(item); }}>
                        <Icon name="close" size={13} />
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {pinnedConversations.length === 0 && recentConversations.length === 0 && (
              <p className="app-history-empty">{t("chat.searchEmpty")}</p>
            )}
          </>
        )}
      </div>
      <div className="app-sidebar-bottom">
        <div className="app-profile">
          <span className="app-avatar" aria-hidden="true">{displayName.charAt(0).toUpperCase()}</span>
          <span className="app-profile-name" title={displayName}>{displayName}</span>
        </div>
        <button className="app-nav-link app-logout" type="button" onClick={onLogout}>
          <Icon name="external" size={18} />{t("nav.logout")}
        </button>
      </div>
    </>
  );

  return (
    <div className={`app-shell theme-${theme} ${sidebarOpen ? "" : "sidebar-collapsed"}`}>
      {mobileOpen && <button className="app-drawer-scrim" type="button" aria-label={t("chat.closeNavigation")} onClick={() => setMobileOpen(false)} />}
      <aside ref={sidebarRef} className={`app-sidebar ${mobileOpen ? "is-open" : ""}`} id="app-navigation" aria-label={t("chat.navigation")}>
        {navContent}
      </aside>
      <div className="app-main">
        <header className="app-topbar">
          <button ref={menuButtonRef} className="app-icon-button app-menu-button" type="button" aria-label={mobileOpen || sidebarOpen ? t("chat.closeNavigation") : t("chat.openNavigation")} aria-expanded={mobileOpen || sidebarOpen} aria-controls="app-navigation" onClick={() => {
            if (window.innerWidth <= 820) setMobileOpen((open) => !open);
            else setSidebarOpen((open) => !open);
          }}>
            <Icon name={mobileOpen || !sidebarOpen ? "close" : "menu"} size={21} />
          </button>
          <div className="app-topbar-title">
            <span className="app-eyebrow">{t("chat.workspace")}</span>
            <h1>{isChatRoute ? (conversation?.title || t("chat.newChat")) : isVoiceRoute ? t("voice.title") : isDocumentsRoute ? t("documents.title") : isSettingsRoute ? t("settings.title") : t("chat.dashboard")}</h1>
          </div>
          <div className="app-topbar-controls">
            <LanguageSwitcher />
            <ThemeToggle />
          </div>
        </header>

        {authError && (
          <div className="app-auth-alert" role="alert">
            <span>{t(`auth.${authError}`)}</span>
            <button type="button" className="link-button" onClick={onDismissAuthError}>{t("common.dismiss")}</button>
          </div>
        )}

        {isChatRoute ? (
          <ConversationPanel
            key={routeId || "new"}
            conversation={conversation}
            conversationMissing={conversationMissing}
            sending={Boolean(routeId && sendingIds.has(routeId))}
            error={conversation?.error}
            operationError={conversationStartError || workspaceLoadError}
            documents={documents}
            selectedAttachments={selectedAttachments}
            onSelectFiles={(files) => Promise.all(files.map((file) => uploadFile(file, { attachToChat: true })))}
            onRemoveAttachment={removeDocument}
            onSend={handleSend}
            onRetry={retryLastMessage}
            onNewChat={startNewChat}
            onVoiceConversation={startVoiceConversation}
          />
        ) : isDocumentsRoute ? (
          <Documents documents={documents} loadError={documentsLoadError} onUpload={(file) => uploadFile(file)} onRetry={(document) => uploadFile(document.file, { retryId: document.localId })} onRemove={removeDocument} onAttach={attachDocument} />
        ) : isVoiceRoute ? (
          <Voice conversation={activeConversation} conversations={conversations} conversationId={activeConversation?.id || ""} sending={currentSending} onSend={handleVoiceSend} onNewConversation={startVoiceConversation} onSelectConversation={setActiveConversationId} onExit={exitVoice} error={chatError} />
        ) : isSettingsRoute ? (
          <Settings user={user} onLogout={onLogout} />
        ) : (
          <section className="dashboard-home" aria-labelledby="dashboard-welcome">
            <div className="dashboard-welcome">
              <p className="app-eyebrow">{t("chat.workspace")}</p>
              <h2 id="dashboard-welcome">{t("chat.welcome", { name: displayName.split("@")[0] })}</h2>
              <p>{t("chat.dashboardIntro")}</p>
              <button className="app-button app-button-primary" type="button" onClick={startNewChat}>
                <Icon name="plus" size={19} />{t("chat.startConversation")}
              </button>
            </div>
            <div className="dashboard-recent">
              <div className="dashboard-section-head">
                <div><p className="app-eyebrow">{t("chat.workspace")}</p><h2>{t("chat.recent")}</h2></div>
                {conversations.length > 0 && <button className="app-button app-button-quiet" type="button" onClick={startNewChat}><Icon name="plus" size={17} />{t("chat.newChat")}</button>}
              </div>
              {conversations.length === 0 ? (
                <p className="dashboard-no-recent">{t("chat.noHistory")}</p>
              ) : (
                <ul className="dashboard-conversation-list">
                  {conversations.map((item) => (
                    <li key={item.id}>
                      <button type="button" onClick={() => { setActiveConversationId(item.id); navigate(`/app/chat/${encodeURIComponent(item.id)}`); }}>
                        <span className="icon-badge" aria-hidden="true"><Icon name="message" size={19} /></span>
                        <span className="dashboard-conversation-copy"><strong>{item.title}</strong><small>{t("chat.messageCount", { count: item.messages.filter((message) => message.role === "user").length })}</small></span>
                        <Icon name="arrow" size={17} className="icon-flip" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}