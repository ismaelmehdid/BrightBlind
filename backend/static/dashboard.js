const $ = (selector) => document.querySelector(selector);
const pollDelay = 1500;
let token = '';
let polling;
let pollTimer;
let lastImage = null;

async function request(path, { body, signal } = {}) {
    const headers = {};
    if (token) headers.Authorization = 'Bearer ' + token;
    if (body !== undefined) headers['Content-Type'] = 'application/json';

    const response = await fetch(path, {
        method: body === undefined ? 'GET' : 'POST',
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: signal || AbortSignal.timeout(10000),
    });
    if (!response.ok) {
        const data = await response.json().catch(() => null);
        const detail = typeof data?.detail === 'string' ? data.detail : null;
        throw new Error(response.status === 401
            ? 'Enter your team dashboard token.'
            : detail || 'Server returned ' + response.status);
    }
    return response.json();
}

function setText(selector, text) {
    const element = $(selector);
    if (element.textContent !== text) element.textContent = text;
}

function clearImage() {
    lastImage = null;
    $('#frame').removeAttribute('src');
    $('#frame').hidden = true;
    $('#empty').hidden = false;
    setText('#frameTime', 'Only frames selected for analysis appear here.');
}

function renderState(state) {
    setText('#connection', state.clients.length ? state.clients.join(' + ') + ' connected' : 'Waiting for relays');
    $('#providers').replaceChildren(...Object.entries(state.providers).map(([name, configured]) => {
        const provider = document.createElement('span');
        provider.textContent = name + ' · ' + (configured ? 'configured' : 'needs setup');
        if (configured) provider.className = 'ready';
        return provider;
    }));
    setText('#scene', state.scene + (state.streaming ? ' · streaming' : ''));
    if (!state.image) {
        clearImage();
    } else if (state.image.ts !== lastImage) {
        lastImage = state.image.ts;
        $('#frame').src = 'data:image/jpeg;base64,' + state.image.jpeg_b64;
        $('#frame').hidden = false;
        $('#empty').hidden = true;
        setText('#frameTime', 'Captured ' + new Date(state.image.ts).toLocaleTimeString() + ' · ' + state.image.scene);
    }

    const route = state.transit;
    const time = route?.departure_time ? new Date(route.departure_time) : null;
    const departure = time && Number.isFinite(time.getTime())
        ? ' · estimated departure ' + time.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
        : ' · no departure estimate';
    setText('#route', route
        ? 'Line ' + route.line + ' · ' + route.stop + departure
        : 'No Google Maps route has been requested.');

    $('#events').replaceChildren(...state.events.map((event) => {
        const row = document.createElement('li');
        const meta = document.createElement('small');
        const detail = document.createElement('p');
        meta.textContent = event.agent + ' / ' + event.event + ' · ' + new Date(event.ts).toLocaleTimeString();
        detail.textContent = String(event.detail || '');
        row.append(meta, detail);
        return row;
    }));
}

function clearState() {
    clearImage();
    $('#providers').replaceChildren();
    $('#events').replaceChildren();
    setText('#scene', 'Waiting for a view');
    setText('#route', 'No Google Maps route has been requested.');
}

async function refresh() {
    const controller = new AbortController();
    polling = controller;
    const deadline = setTimeout(() => controller.abort(), 10000);
    try {
        const state = await request('/api/state', { signal: controller.signal });
        if (polling === controller) renderState(state);
    } catch (error) {
        if (polling !== controller) return;
        clearState();
        setText('#connection', controller.signal.aborted ? 'Dashboard request timed out.' : error.message);
    } finally {
        clearTimeout(deadline);
        if (polling === controller) {
            polling = null;
            pollTimer = setTimeout(refresh, pollDelay);
        }
    }
}

$('#access').onsubmit = (event) => {
    event.preventDefault();
    token = $('#token').value.trim();
    clearTimeout(pollTimer);
    polling?.abort();
    clearState();
    setText('#connection', 'Connecting…');
    void refresh();
};

$('#question').onsubmit = async (event) => {
    event.preventDefault();
    const text = $('#text').value.trim();
    if (!text) return;
    const button = $('#question button');
    button.disabled = true;
    try {
        await request('/api/question', { body: { text } });
        setText('#notice', 'Request sent through Pipecat.');
    } catch (error) {
        setText('#notice', error.message);
    } finally {
        button.disabled = false;
    }
};

$('#stop').onclick = async () => {
    try {
        await request('/api/stop', { body: {} });
        setText('#notice', 'Camera tasks and speech stopped.');
    } catch (error) {
        setText('#notice', error.message);
    }
};

void refresh();
