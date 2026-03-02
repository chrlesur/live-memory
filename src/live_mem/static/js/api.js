/**
 * Live Memory - API REST avec auth Bearer Token
 */

const AUTH_TOKEN_KEY = 'livemem_auth_token';

function getAuthToken() { return localStorage.getItem(AUTH_TOKEN_KEY); }
function setAuthToken(token) { localStorage.setItem(AUTH_TOKEN_KEY, token); }
function clearAuthToken() { localStorage.removeItem(AUTH_TOKEN_KEY); }

function authHeaders(extra = {}) {
    const token = getAuthToken();
    return token ? { ...extra, 'Authorization': `Bearer ${token}` } : extra;
}

/**
 * Fetch avec gestion auto du 401 et parsing JSON robuste.
 */
async function authFetch(url, options = {}) {
    options.headers = authHeaders(options.headers || {});

    let response;
    try {
        response = await fetch(url, options);
    } catch (e) {
        console.error(`[API] Network error: ${url}`, e);
        return { status: 'error', message: 'Erreur réseau' };
    }

    if (response.status === 401) {
        clearAuthToken();
        showLogin('Session expirée.');
        throw new Error('Unauthorized');
    }

    // Parser le JSON de manière robuste (gère les réponses vides/tronquées)
    try {
        const text = await response.text();
        if (!text) return { status: 'error', message: 'Réponse vide du serveur' };
        return JSON.parse(text);
    } catch (e) {
        console.error(`[API] JSON parse error: ${url}`, e);
        return { status: 'error', message: 'Réponse invalide du serveur' };
    }
}

// ═══════════════ ENDPOINTS ═══════════════

async function apiLoadSpaces() {
    return await authFetch('/api/spaces');
}

async function apiLoadSpaceInfo(spaceId) {
    return await authFetch(`/api/space/${encodeURIComponent(spaceId)}`);
}

async function apiLoadNotes(spaceId, params = {}) {
    const qs = new URLSearchParams();
    if (params.limit) qs.set('limit', params.limit);
    if (params.agent) qs.set('agent', params.agent);
    if (params.category) qs.set('category', params.category);
    const qsStr = qs.toString();
    return await authFetch(`/api/live/${encodeURIComponent(spaceId)}${qsStr ? '?' + qsStr : ''}`);
}

async function apiLoadBankList(spaceId) {
    return await authFetch(`/api/bank/${encodeURIComponent(spaceId)}`);
}

async function apiLoadBankFile(spaceId, filename) {
    return await authFetch(`/api/bank/${encodeURIComponent(spaceId)}/${encodeURIComponent(filename)}`);
}
