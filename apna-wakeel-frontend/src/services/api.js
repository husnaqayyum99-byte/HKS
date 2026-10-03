// -----------------------------------------------------------------------------
// API SERVICE
// Uses the routes and schemas actually published by the FastAPI backend.
// -----------------------------------------------------------------------------

import { API_BASE_URL } from "../lib/apiConfig.js";
import { getStoredSession, persistSession, refreshSession } from "./auth.js";

const BASE_URL = API_BASE_URL;
let openApiPromise;

function apiError(payload, status) {
  const detail = payload?.detail;
  const message = typeof detail === "string"
    ? detail
    : status === 401
      ? "api.unauthorized"
      : status === 403
        ? "api.forbidden"
        : status === 404
          ? "api.endpointUnavailable"
          : status === 422
            ? "api.invalidRequest"
            : status === 429
              ? "api.rateLimited"
              : status >= 500
                ? "api.serverError"
                : "api.requestFailed";
  const error = new Error(message);
  error.status = status;
  return error;
}

export async function assertApiRoute(path, method) {
  if (!BASE_URL) {
    const error = new Error("api.notConfigured");
    error.status = 0;
    throw error;
  }

  if (!openApiPromise) {
    openApiPromise = fetch(`${BASE_URL}/openapi.json`)
      .then((response) => {
        if (!response.ok) throw apiError({}, response.status);
        return response.json();
      })
      .catch((error) => {
        openApiPromise = null;
        throw error;
      });
  }

  const schema = await openApiPromise;
  if (!schema.paths?.[path]?.[method.toLowerCase()]) {
    const error = new Error("api.endpointUnavailable");
    error.status = 404;
    throw error;
  }
}

function buildHeaders(accessToken, includeJson = true) {
  const headers = includeJson ? { "Content-Type": "application/json" } : {};
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  return headers;
}

export async function fetchWithSessionRefresh(url, options, accessToken, includeJson = true) {
  const storedSession = getStoredSession();
  const token = storedSession?.access_token || accessToken || "";
  const response = await fetch(url, { ...options, headers: buildHeaders(token, includeJson) });

  if (response.status !== 401) return response;

  const session = getStoredSession();
  if (!session?.refresh_token) return response;

  try {
    if (session.access_token !== token) {
      return fetch(url, { ...options, headers: buildHeaders(session.access_token, includeJson) });
    }
    const refreshed = await refreshSession(session.refresh_token);
    return fetch(url, { ...options, headers: buildHeaders(refreshed.access_token, includeJson) });
  } catch {
    persistSession(null);
    return response;
  }

}

async function getJson(path, accessToken) {
  const response = await fetchWithSessionRefresh(`${BASE_URL}${path}`, { method: "GET" }, accessToken, false);
  if (!response.ok) throw apiError(await response.json().catch(() => ({})), response.status);
  return response.json();
}

async function postJson(path, body, accessToken) {
  const response = await fetchWithSessionRefresh(
    `${BASE_URL}${path}`,
    { method: "POST", body: JSON.stringify(body) },
    accessToken,
    true,
  );
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw apiError(payload, response.status);
  return payload;
}

async function deleteJson(path, accessToken) {
  const response = await fetchWithSessionRefresh(`${BASE_URL}${path}`, { method: "DELETE" }, accessToken, false);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw apiError(payload, response.status);
  return payload;
}

export async function createConversation({ title, accessToken }) {
  if (!BASE_URL) throw new Error("chat_not_connected");
  return (await postJson("/api/conversations", { title }, accessToken)).data;
}

export async function listConversations({ accessToken }) {
  if (!BASE_URL) throw new Error("chat_not_connected");
  return (await getJson("/api/conversations", accessToken)).data || [];
}

export async function getConversation({ conversationId, accessToken }) {
  if (!BASE_URL) throw new Error("chat_not_connected");
  return (await getJson(`/api/conversations/${encodeURIComponent(conversationId)}`, accessToken)).data;
}

export async function getConversationMessages({ conversationId, accessToken }) {
  if (!BASE_URL) throw new Error("chat_not_connected");
  return (await getJson(`/api/conversations/${encodeURIComponent(conversationId)}/messages`, accessToken)).data || [];
}

export async function sendConversationMessage({ conversationId, content, language = "en", labels = {}, documentIds = [], accessToken }) {
  if (!BASE_URL) throw new Error("chat_not_connected");
  return postJson(`/api/conversations/${encodeURIComponent(conversationId)}/messages`, {
    content,
    language,
    labels,
    document_ids: documentIds,
  }, accessToken);
}

export async function deleteConversation({ conversationId, accessToken }) {
  if (!BASE_URL) throw new Error("chat_not_connected");
  return deleteJson(`/api/conversations/${encodeURIComponent(conversationId)}`, accessToken);
}

export async function sendChatMessage({ conversationId, messages, language = "en", labels = {}, documentIds = [], newChatTitle, accessToken }) {
  if (!BASE_URL) throw new Error("chat_not_connected");
  const content = messages[messages.length - 1]?.content || "";
  if (!content.trim()) throw new Error("chat_invalid_response");

  let targetConversationId = conversationId;
  if (!targetConversationId) {
    targetConversationId = (await createConversation({ title: newChatTitle, accessToken })).id;
  }

  const payload = await sendConversationMessage({ conversationId: targetConversationId, content, language, labels, documentIds, accessToken });
  return {
    conversationId: targetConversationId,
    message: { role: "assistant", content: payload.assistant_message?.content || "" },
  };
}

export async function analyzePublicCase({ content, language = "en", conversationHistory = [] }) {
  if (!BASE_URL) throw new Error("api.notConfigured");
  await assertApiRoute("/api/public-analysis", "post");

  const response = await fetch(`${BASE_URL}/api/public-analysis`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      content,
      language,
      conversation_history: conversationHistory,
    }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw apiError(payload, response.status);
  return payload;
}
