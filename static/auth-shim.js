/* =========================================================================
   NEXUZ AUTH SHIM  (additive file - script.js is NOT modified)
   -------------------------------------------------------------------------
   Load it BEFORE script.js.  What it does:
     1. After /api/login or /api/register succeeds, it stores the signed token
        the server returns (localStorage key: nexuz_auth_token).
     2. It adds  Authorization: Bearer <token>  to every /api/... request, and
        adds ?token=... to the /ws/live WebSocket - so the server knows who you
        really are (admin panel, messages, profile, chat memory, live voice).
     3. If a saved login has no token (you logged in before this update) it logs
        you out once so you can sign in again and get a token.
     4. If the server answers 401 (expired / invalid token) it clears the session
        and reloads once so the login screen appears.
   Set  NEXUZ_AUTH.forceRelogin = false  (before script.js loads) to skip step 3.
   ========================================================================= */
(function () {
    'use strict';
    const TOKEN_KEY = 'nexuz_auth_token';
    const USER_KEY = 'nexuz_user_data';           // the key script.js uses for the logged-in user
    const CFG = window.NEXUZ_AUTH = window.NEXUZ_AUTH || { forceRelogin: true };

    const store = {
        get(k) { try { return localStorage.getItem(k) || ''; } catch (e) { return ''; } },
        set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* storage blocked */ } },
        del(k) { try { localStorage.removeItem(k); } catch (e) { /* ignore */ } }
    };

    // --- keep token and user session in sync (runs before script.js reads the saved user) ---
    if (store.get(USER_KEY) && !store.get(TOKEN_KEY) && CFG.forceRelogin) store.del(USER_KEY);   // old session without token
    if (!store.get(USER_KEY) && store.get(TOKEN_KEY)) store.del(TOKEN_KEY);                       // logged out earlier

    const isApi = (url) => {
        try {
            const u = new URL(url, window.location.origin);
            return u.origin === window.location.origin && u.pathname.startsWith('/api/');
        } catch (e) { return false; }
    };

    // --- fetch wrapper ---
    const origFetch = window.fetch.bind(window);
    window.fetch = async function (input, init) {
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        const api = isApi(url);
        const sentToken = api ? store.get(TOKEN_KEY) : '';
        if (api && sentToken) {
            init = Object.assign({}, init);
            const headers = new Headers(init.headers || (input && input.headers) || undefined);
            if (!headers.has('Authorization')) headers.set('Authorization', 'Bearer ' + sentToken);
            init.headers = headers;
        }
        const res = await origFetch(input, init);
        if (api) {
            if (/\/api\/(login|register)(\?|$)/.test(url)) {
                try {
                    const data = await res.clone().json();      // stored BEFORE script.js receives the response
                    if (data && data.success && data.token) store.set(TOKEN_KEY, data.token);
                } catch (e) { /* not JSON */ }
            } else if (res.status === 401 && sentToken) {
                store.del(TOKEN_KEY);
                store.del(USER_KEY);
                try {
                    if (!sessionStorage.getItem('nexuz_401_reload')) {
                        sessionStorage.setItem('nexuz_401_reload', '1');
                        window.location.reload();
                    }
                } catch (e) { /* ignore */ }
            }
        }
        return res;
    };
    try { sessionStorage.removeItem('nexuz_401_reload'); } catch (e) { /* ignore */ }

    // --- WebSocket wrapper (browsers cannot set headers on WebSocket, so the token goes in the query string) ---
    const OrigWS = window.WebSocket;
    if (OrigWS) {
        const WrappedWS = function (url, protocols) {
            let finalUrl = url;
            try {
                const t = store.get(TOKEN_KEY);
                if (t && /\/ws\/live(\?|$)/.test(String(url))) {
                    finalUrl = String(url) + (String(url).indexOf('?') === -1 ? '?' : '&') + 'token=' + encodeURIComponent(t);
                }
            } catch (e) { finalUrl = url; }
            return protocols === undefined ? new OrigWS(finalUrl) : new OrigWS(finalUrl, protocols);
        };
        WrappedWS.prototype = OrigWS.prototype;
        ['CONNECTING', 'OPEN', 'CLOSING', 'CLOSED'].forEach((k) => { WrappedWS[k] = OrigWS[k]; });
        window.WebSocket = WrappedWS;
    }
})();
