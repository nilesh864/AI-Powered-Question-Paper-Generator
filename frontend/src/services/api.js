import axios from 'axios';

const API_ROOT = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
const WORKSPACE_EVENTS_KEY = 'qps-workspace-events';

function workspaceEventsKey() {
  return `${WORKSPACE_EVENTS_KEY}:${localStorage.getItem('qps-user-id') || 'anonymous'}`;
}

const client = axios.create({
  baseURL: API_ROOT,
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('qps-token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  if (typeof config.data === 'string' && !config.headers['Content-Type']) {
    config.headers['Content-Type'] = 'application/json';
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  (error) => {
    const requestPath = error.config?.url || '';
    if (error.response?.status === 401 && !requestPath.startsWith('/auth/')) {
      window.dispatchEvent(new Event('qps:unauthorized'));
    }
    return Promise.reject(error);
  }
);

export async function apiRequest(path, options = {}) {
  const { body, ...config } = options;
  try {
    const response = await client.request({
      url: path,
      ...config,
      data: body,
      responseType: path.startsWith('/export/') ? 'blob' : 'json',
    });
    if (response.status === 204) return null;
    return response.data;
  } catch (error) {
    let responseBody = error.response?.data;
    if (responseBody instanceof Blob) {
      try {
        responseBody = JSON.parse(await responseBody.text());
      } catch {
        responseBody = {};
      }
    }
    const requestError = new Error(responseBody?.detail || error.message || 'Request failed');
    requestError.statusCode = error.response?.status;
    throw requestError;
  }
}

export function saveDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.style.position = 'fixed';
  anchor.style.left = '-10000px';
  document.body.appendChild(anchor);
  anchor.click();
  window.setTimeout(() => {
    URL.revokeObjectURL(url);
    anchor.remove();
  }, 1000);
}

export function recordWorkspaceEvent(title, detail) {
  let events = [];
  try {
    events = JSON.parse(localStorage.getItem(workspaceEventsKey()) || '[]');
  } catch {
    events = [];
  }
  const event = { id: `${Date.now()}-${Math.random().toString(16).slice(2)}`, title, detail, createdAt: new Date().toISOString(), read: false };
  localStorage.setItem(workspaceEventsKey(), JSON.stringify([event, ...events].slice(0, 30)));
  window.dispatchEvent(new CustomEvent('qps:workspace-event', { detail: event }));
}

export function readWorkspaceEvents() {
  try {
    return JSON.parse(localStorage.getItem(workspaceEventsKey()) || '[]');
  } catch {
    return [];
  }
}

export function markWorkspaceEventsRead() {
  const events = readWorkspaceEvents().map((event) => ({ ...event, read: true }));
  localStorage.setItem(workspaceEventsKey(), JSON.stringify(events));
  window.dispatchEvent(new Event('qps:workspace-event'));
}

export default client;