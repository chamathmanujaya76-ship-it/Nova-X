/* =========================================================================
   NEXUZ WIREFRAME VISUALIZER  (add-on module)
   -------------------------------------------------------------------------
   Load this AFTER script.js. It does NOT edit or delete anything in
   script.js / app.py / style.css. It only replaces the *drawing* of the
   Live Voice canvas by re-pointing two function names:
       initThreeGlowVisualizer()  and  visualizeAudio()
   Everything else (speech recognition, WebSocket, TTS, login, chat...) is
   untouched and keeps working exactly as before.

   Modes (Settings > Nexuz Voice > Live Voice Mode Display Type):
       "face"   -> glowing blue wireframe face built from /static/face.glb
       "sphere" -> glowing blue/purple/pink wavy wireframe orb
   To go back to your old particle visualizer: NEXUZ_WIRE.enabled = false
   ========================================================================= */
(function () {
    'use strict';

    const WIRE = {
        enabled: true,
        glbUrl: '/static/face.glb',
        faceHeight: 190,
        sphereRadius: 88,
        sphereLat: 56,
        sphereLon: 84,
        haloCount: 1700,
        shardCount: 240,
        tintBackground: true
    };
    window.NEXUZ_WIRE = WIRE;

    const origInit = window.initThreeGlowVisualizer;
    const origVis = window.visualizeAudio;

    // ---- safe accessors for the globals that live in script.js -------------
    const isLive = () => (typeof isLiveVoiceActive !== 'undefined') && isLiveVoiceActive;
    const aiSpeaking = () => (typeof isAiSpeaking !== 'undefined') && isAiSpeaking;
    const getMode = () => {
        try {
            const t = (typeof currentUser !== 'undefined' && currentUser) ? currentUser.display_type : 'face';
            return t === 'sphere' ? 'sphere' : 'face';
        } catch (e) { return 'face'; }
    };

    // ---- math helpers ------------------------------------------------------
    const clamp = (v, a, b) => (v < a ? a : (v > b ? b : v));
    const smooth = (e0, e1, x) => { const t = clamp((x - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t); };
    const easeOut = (t) => 1 - Math.pow(1 - t, 3);

    // ---- state -------------------------------------------------------------
    const W = {
        ready: false, failed: false, raf: 0, last: 0,
        renderer: null, scene: null, camera: null, root: null,
        mode: 'face', mix: 0, level: 0, userPulse: 0,
        sphere: null, halo: null, face: null, shards: null,
        listenersAdded: false
    };

    // ---- audio tap: real lip-sync from the TTS audio (best effort) ---------
    let aCtx = null, aNode = null, aData = null, tapActive = false;
    const tapped = new WeakSet();

    function primeAudio() {
        try {
            if (aCtx) { if (aCtx.state === 'suspended') aCtx.resume(); return; }
            const AC = window.AudioContext || window.webkitAudioContext;
            if (!AC) return;
            aCtx = new AC();
            aNode = aCtx.createAnalyser();
            aNode.fftSize = 256;
            aNode.smoothingTimeConstant = 0.55;
            aNode.connect(aCtx.destination);
            aData = new Uint8Array(aNode.frequencyBinCount);
            if (aCtx.state === 'suspended') aCtx.resume();
        } catch (e) { aCtx = null; }
    }
    ['pointerdown', 'keydown', 'touchstart', 'click'].forEach((ev) =>
        document.addEventListener(ev, primeAudio, { capture: true, passive: true }));

    function tapAudio(el) {
        try {
            if (!isLive() || !aCtx || aCtx.state !== 'running') return;   // otherwise leave audio alone
            if (!(el instanceof HTMLAudioElement) || tapped.has(el)) return;
            tapped.add(el);
            const src = aCtx.createMediaElementSource(el);
            src.connect(aNode);
            tapActive = true;
            const off = () => { tapActive = false; try { src.disconnect(); } catch (e) {} };
            el.addEventListener('ended', off);
            el.addEventListener('error', off);
        } catch (e) { tapActive = false; }
    }
    const origPlay = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = function () {
        tapAudio(this);
        return origPlay.apply(this, arguments);
    };

    // user speech pulse: the live transcript box changes while the user talks
    function watchTranscript() {
        const el = document.getElementById('liveTranscript');
        if (!el || el.__wireWatched || typeof MutationObserver === 'undefined') return;
        el.__wireWatched = true;
        new MutationObserver(() => { W.userPulse = 1; })
            .observe(el, { childList: true, characterData: true, subtree: true });
    }

    function realLevel() {
        aNode.getByteFrequencyData(aData);
        let s = 0;
        for (let i = 1; i < 33; i++) s += aData[i];
        return clamp((s / 32 / 255) * 2.4, 0, 1);
    }

    function updateLevel(t, dt) {
        let target = 0;
        if (aiSpeaking()) {
            if (tapActive && aNode) target = realLevel();
            else target = clamp(0.28 + 0.45 * Math.abs(Math.sin(t * 7.3)) * Math.abs(Math.sin(t * 3.1 + 1)) + 0.12 * Math.sin(t * 17), 0, 1);
        } else if (W.userPulse > 0.02) {
            target = W.userPulse * 0.55;
        }
        W.userPulse *= Math.pow(0.9, dt * 60);
        W.level += (target - W.level) * (target > W.level ? 0.35 : 0.12);
    }

    // ---- textures ----------------------------------------------------------
    function dotTexture() {
        const c = document.createElement('canvas');
        c.width = c.height = 32;
        const x = c.getContext('2d');
        const g = x.createRadialGradient(16, 16, 0, 16, 16, 16);
        g.addColorStop(0, 'rgba(255,255,255,1)');
        g.addColorStop(0.35, 'rgba(255,255,255,0.55)');
        g.addColorStop(1, 'rgba(255,255,255,0)');
        x.fillStyle = g; x.fillRect(0, 0, 32, 32);
        const tex = new THREE.Texture(c);
        tex.needsUpdate = true;
        return tex;
    }

    // blue -> violet -> magenta (like the orb reference)
    function gradient(s, out, o) {
        let r, g, b;
        if (s < 0.5) { const k = s / 0.5; r = 0.10 + 0.40 * k; g = 0.45 - 0.25 * k; b = 1.0; }
        else { const k = (s - 0.5) / 0.5; r = 0.50 + 0.50 * k; g = 0.20 + 0.05 * k; b = 1.0 - 0.15 * k; }
        out[o] = r; out[o + 1] = g; out[o + 2] = b;
    }

    // ---- SPHERE ------------------------------------------------------------
    function buildSphere() {
        const nLat = WIRE.sphereLat, nLon = WIRE.sphereLon;
        const count = (nLat + 1) * nLon;
        const dirs = new Float32Array(count * 3);
        const pos = new Float32Array(count * 3);
        const col = new Float32Array(count * 3);
        let k = 0;
        for (let i = 0; i <= nLat; i++) {
            const phi = Math.PI * i / nLat, sp = Math.sin(phi), cp = Math.cos(phi);
            for (let j = 0; j < nLon; j++) {
                const th = 2 * Math.PI * j / nLon;
                const dx = sp * Math.cos(th), dy = cp, dz = sp * Math.sin(th);
                dirs[k] = dx; dirs[k + 1] = dy; dirs[k + 2] = dz;
                gradient(clamp(0.5 + 0.5 * (0.6 * dx - 0.8 * dy), 0, 1), col, k);
                k += 3;
            }
        }
        const idx = [];
        for (let i = 0; i <= nLat; i++) {
            for (let j = 0; j < nLon; j++) {
                const a = i * nLon + j;
                if (i > 0 && i < nLat) idx.push(a, i * nLon + ((j + 1) % nLon));
                if (i < nLat) idx.push(a, (i + 1) * nLon + j);
            }
        }
        const geo = new THREE.BufferGeometry();
        const pa = new THREE.BufferAttribute(pos, 3);
        pa.setUsage(THREE.DynamicDrawUsage);
        geo.setAttribute('position', pa);
        geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
        geo.setIndex(idx);
        const mat = new THREE.LineBasicMaterial({
            vertexColors: true, transparent: true, opacity: 0.8,
            blending: THREE.AdditiveBlending, depthWrite: false
        });
        const lines = new THREE.LineSegments(geo, mat);
        const group = new THREE.Group();
        group.add(lines);
        return { group, lines, geo, mat, dirs, pos, pa, count };
    }

    function buildHalo() {
        const n = WIRE.haloCount;
        const pos = new Float32Array(n * 3), col = new Float32Array(n * 3);
        for (let i = 0; i < n; i++) {
            const th = Math.random() * Math.PI * 2, ph = Math.acos(2 * Math.random() - 1);
            const r = WIRE.sphereRadius * (1.12 + Math.pow(Math.random(), 1.6) * 0.65);
            const dx = Math.sin(ph) * Math.cos(th), dy = Math.cos(ph), dz = Math.sin(ph) * Math.sin(th);
            pos[i * 3] = dx * r; pos[i * 3 + 1] = dy * r; pos[i * 3 + 2] = dz * r;
            gradient(clamp(0.5 + 0.5 * (0.6 * dx - 0.8 * dy), 0, 1), col, i * 3);
        }
        const geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
        geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
        const mat = new THREE.PointsMaterial({
            size: 2.4, map: dotTexture(), vertexColors: true, transparent: true, opacity: 0.9,
            blending: THREE.AdditiveBlending, depthWrite: false
        });
        const pts = new THREE.Points(geo, mat);
        return { pts, geo, mat };
    }

    function updateSphere(t, level) {
        const S = W.sphere, R = WIRE.sphereRadius, d = S.dirs, p = S.pos;
        const amp = 0.07 + 0.22 * level;
        for (let i = 0, n = S.count * 3; i < n; i += 3) {
            const dx = d[i], dy = d[i + 1], dz = d[i + 2];
            const w = Math.sin(dx * 3.2 + t * 0.8) * Math.cos(dy * 2.6 - t * 0.6)
                + 0.65 * Math.sin(dz * 4.1 + dx * 1.7 + t * 1.15)
                + 0.7 * level * Math.sin((dx + dy + dz) * 6.0 - t * 2.4);
            const r = R * (1 + amp * w * 0.55);
            p[i] = dx * r; p[i + 1] = dy * r; p[i + 2] = dz * r;
        }
        S.pa.needsUpdate = true;
        S.group.rotation.y = t * 0.12;
        S.group.rotation.x = Math.sin(t * 0.3) * 0.12;
        W.halo.pts.rotation.y = -t * 0.05;
        W.halo.pts.scale.setScalar(1 + 0.08 * level);
    }

    // ---- FACE (from face.glb) ----------------------------------------------
    function buildFace(gltf) {
        gltf.scene.updateMatrixWorld(true);
        let mesh = null;
        gltf.scene.traverse((c) => {
            if (!mesh && c.isMesh && c.geometry && c.geometry.index && c.geometry.attributes.position) mesh = c;
        });
        if (!mesh) throw new Error('face.glb has no indexed mesh');

        const g = mesh.geometry, pa = g.attributes.position, ia = g.index.array;
        const n = pa.count, v = new THREE.Vector3();
        const rest = new Float32Array(n * 3);
        let mn = [Infinity, Infinity, Infinity], mx = [-Infinity, -Infinity, -Infinity];
        for (let j = 0; j < n; j++) {
            v.fromBufferAttribute(pa, j).applyMatrix4(mesh.matrixWorld);
            rest[j * 3] = v.x; rest[j * 3 + 1] = v.y; rest[j * 3 + 2] = v.z;
            if (v.x < mn[0]) mn[0] = v.x; if (v.y < mn[1]) mn[1] = v.y; if (v.z < mn[2]) mn[2] = v.z;
            if (v.x > mx[0]) mx[0] = v.x; if (v.y > mx[1]) mx[1] = v.y; if (v.z > mx[2]) mx[2] = v.z;
        }
        const cx = (mn[0] + mx[0]) / 2, cy = (mn[1] + mx[1]) / 2, cz = (mn[2] + mx[2]) / 2;
        const sc = WIRE.faceHeight / (mx[1] - mn[1]);
        for (let j = 0; j < n; j++) {
            rest[j * 3] = (rest[j * 3] - cx) * sc;
            rest[j * 3 + 1] = (rest[j * 3 + 1] - cy) * sc;
            rest[j * 3 + 2] = (rest[j * 3 + 2] - cz) * sc;
        }

        // The mesh is a triangulated quad mesh: drop the diagonals so it looks like a clean grid.
        const key = (a, b) => (a < b ? a * n + b : b * n + a);
        const diag = new Set();
        for (let i = 0; i + 5 < ia.length; i += 6) {
            const A = [ia[i], ia[i + 1], ia[i + 2]], B = [ia[i + 3], ia[i + 4], ia[i + 5]];
            const sh = A.filter((x) => B.indexOf(x) !== -1);
            if (sh.length === 2) diag.add(key(sh[0], sh[1]));
        }
        const seen = new Set(), edges = [];
        for (let i = 0; i + 2 < ia.length; i += 3) {
            for (let e = 0; e < 3; e++) {
                const a = ia[i + e], b = ia[i + (e + 1) % 3], k = key(a, b);
                if (diag.has(k) || seen.has(k)) continue;
                seen.add(k); edges.push(a, b);
            }
        }

        const cur = new Float32Array(n * 3), scatter = new Float32Array(n * 3);
        const col = new Float32Array(n * 3), stagger = new Float32Array(n);
        for (let j = 0; j < n; j++) {
            const th = Math.random() * Math.PI * 2, ph = Math.acos(2 * Math.random() - 1), r = 220 + Math.random() * 220;
            scatter[j * 3] = r * Math.sin(ph) * Math.cos(th);
            scatter[j * 3 + 1] = r * Math.cos(ph);
            scatter[j * 3 + 2] = r * Math.sin(ph) * Math.sin(th);
            stagger[j] = Math.random();
        }
        cur.set(scatter);

        const posAttr = new THREE.BufferAttribute(cur, 3);
        posAttr.setUsage(THREE.DynamicDrawUsage);
        const colAttr = new THREE.BufferAttribute(col, 3);
        colAttr.setUsage(THREE.DynamicDrawUsage);

        const lineGeo = new THREE.BufferGeometry();
        lineGeo.setAttribute('position', posAttr);
        lineGeo.setAttribute('color', colAttr);
        lineGeo.setIndex(edges);
        const lineMat = new THREE.LineBasicMaterial({
            vertexColors: true, transparent: true, opacity: 0,
            blending: THREE.AdditiveBlending, depthWrite: false
        });
        const lines = new THREE.LineSegments(lineGeo, lineMat);
        lines.renderOrder = 2;

        const fillGeo = new THREE.BufferGeometry();
        fillGeo.setAttribute('position', posAttr);
        fillGeo.setIndex(Array.prototype.slice.call(ia));
        const fillMat = new THREE.MeshBasicMaterial({
            color: 0x05084a, transparent: true, opacity: 0, side: THREE.DoubleSide,
            polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1
        });
        const fill = new THREE.Mesh(fillGeo, fillMat);
        fill.renderOrder = 1;

        const group = new THREE.Group();
        group.add(fill); group.add(lines);
        return { group, lines, fill, lineGeo, fillGeo, lineMat, fillMat, posAttr, colAttr, cur, rest, scatter, col, stagger, n, assembly: 0 };
    }

    const EYE_Y = 18, MOUTH_Y = -47.5, CHIN_Y = -95;

    function updateFace(t, dt, level) {
        const F = W.face, n = F.n, rest = F.rest, cur = F.cur, sc = F.scatter, col = F.col, st = F.stagger;
        F.assembly = Math.min(1, F.assembly + dt * 0.5);
        const asm = F.assembly;
        const open = aiSpeaking() ? clamp(level * 1.25, 0, 1) : 0;      // lips only move while the AI talks
        const ph = t % 4.6, blink = ph < 0.16 ? Math.sin((ph / 0.16) * Math.PI) : 0;
        const scanY = 110 - ((t * 38) % 250);
        const hot = clamp(level * 0.9, 0, 1);

        for (let j = 0, i = 0; j < n; j++, i += 3) {
            let x = rest[i], y = rest[i + 1], z = rest[i + 2];

            if (open > 0.01) {                                 // jaw drop: lower lip + chin move, upper lip stays
                const w = smooth(MOUTH_Y + 1.5, MOUTH_Y - 6, y);       // 0 above the lip line -> 1 on the jaw
                if (w > 0) {
                    const chin = clamp((MOUTH_Y - y) / (MOUTH_Y - CHIN_Y), 0, 1);
                    const side = 1 - 0.55 * smooth(25, 66, Math.abs(x));
                    y -= open * 13 * w * (0.75 + 0.25 * chin) * side;
                    z += open * 2.2 * w * side;
                }
            }
            if (blink > 0.01) {                                // eyelids close toward the eye line
                const ax = Math.abs(x);
                if (ax > 14 && ax < 46 && Math.abs(y - EYE_Y) < 9) {
                    y = EYE_Y + (y - EYE_Y) * (1 - 0.85 * blink);
                }
            }
            z += Math.sin(t * 1.5 + y * 0.05) * 0.6;           // idle shimmer

            const p = easeOut(clamp(asm * 1.4 - st[j] * 0.4, 0, 1));
            cur[i] = sc[i] + (x - sc[i]) * p;
            cur[i + 1] = sc[i + 1] + (y - sc[i + 1]) * p;
            cur[i + 2] = sc[i + 2] + (z - sc[i + 2]) * p;

            const d = y - scanY, scan = Math.exp(-(d * d) / 420);   // bright band sweeping downward
            const k = clamp(0.55 + 0.35 * scan + 0.5 * hot, 0, 1.4);
            const m = clamp(hot * 0.8 + scan * 0.35, 0, 1);
            col[i] = (0.26 + 0.55 * m) * k;
            col[i + 1] = (0.40 + 0.45 * m) * k;
            col[i + 2] = 1.0 * k;
        }
        F.posAttr.needsUpdate = true;
        F.colAttr.needsUpdate = true;
        F.group.rotation.y = Math.sin(t * 0.45) * 0.26;
        F.group.rotation.x = Math.sin(t * 0.33) * 0.05;
    }

    function buildShards() {
        const n = WIRE.shardCount;
        const pos = new Float32Array(n * 3), col = new Float32Array(n * 3), prm = [];
        for (let i = 0; i < n; i++) {
            prm.push({
                r: 80 + Math.random() * 190, a: Math.random() * Math.PI * 2,
                s: (0.08 + Math.random() * 0.35) * (Math.random() < 0.5 ? 1 : -1),
                y: (Math.random() - 0.5) * 280, ph: Math.random() * 6.28
            });
            const b = 0.45 + Math.random() * 0.55;
            col[i * 3] = 0.25 * b; col[i * 3 + 1] = 0.4 * b; col[i * 3 + 2] = b;
        }
        const geo = new THREE.BufferGeometry();
        const pa = new THREE.BufferAttribute(pos, 3);
        pa.setUsage(THREE.DynamicDrawUsage);
        geo.setAttribute('position', pa);
        geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
        const mat = new THREE.PointsMaterial({
            size: 4.2, vertexColors: true, transparent: true, opacity: 0,
            blending: THREE.AdditiveBlending, depthWrite: false
        });
        return { pts: new THREE.Points(geo, mat), geo, mat, pos, pa, prm, n };
    }

    function updateShards(t, dt, level) {
        const H = W.shards, p = H.pos;
        for (let i = 0; i < H.n; i++) {
            const q = H.prm[i];
            q.a += q.s * dt * (1 + level * 3);
            p[i * 3] = Math.cos(q.a) * q.r;
            p[i * 3 + 1] = q.y + Math.sin(t * 0.7 + q.ph) * 8;
            p[i * 3 + 2] = Math.sin(q.a) * q.r * 0.8;
        }
        H.pa.needsUpdate = true;
    }

    // ---- scene setup / teardown -------------------------------------------
    function disposeScene() {
        if (!W.scene) return;
        W.scene.traverse((o) => {
            if (o.geometry) o.geometry.dispose();
            if (o.material) {
                if (o.material.map) o.material.map.dispose();
                o.material.dispose();
            }
        });
        W.scene = null;
    }

    function fitCamera() {
        if (!W.renderer || !W.camera) return;
        const w = window.innerWidth, h = window.innerHeight, aspect = w / h;
        W.camera.aspect = aspect;
        const halfH = W.mode === 'face' ? 100 / 0.8 : (WIRE.sphereRadius * 1.5) / 0.85;
        const halfW = W.mode === 'face' ? 80 : WIRE.sphereRadius * 1.5;
        const tanH = Math.tan((W.camera.fov * Math.PI / 180) / 2);
        const dist = Math.max(halfH / tanH, halfW / (tanH * aspect));
        W.camera.position.set(0, 0, dist);
        W.camera.updateProjectionMatrix();
        W.root.position.y = 2 * dist * tanH * 0.06;           // lift art a little so the status text sits below it
        W.renderer.setSize(w, h);
    }

    function styleForMode() {
        const canvas = document.getElementById('threeGlowCanvas');
        const overlay = document.getElementById('liveVoiceOverlay');
        if (canvas) canvas.style.filter = W.mode === 'face'
            ? 'drop-shadow(0 0 20px rgba(70,100,255,0.75))' : '';
        if (overlay && WIRE.tintBackground) {
            overlay.style.background = W.mode === 'face'
                ? 'radial-gradient(ellipse at 50% 38%, #10139a 0%, #060a52 45%, #00001c 100%)'
                : 'radial-gradient(circle at 50% 40%, #1b0839 0%, #07010f 65%, #000000 100%)';
        }
    }

    function resetStyle() {
        const canvas = document.getElementById('threeGlowCanvas');
        const overlay = document.getElementById('liveVoiceOverlay');
        if (canvas) canvas.style.filter = '';
        if (overlay) overlay.style.background = '';
    }

    function wireInit() {
        const canvas = document.getElementById('threeGlowCanvas');
        if (!canvas) return;
        if (W.raf) { cancelAnimationFrame(W.raf); W.raf = 0; }
        disposeScene();
        watchTranscript();

        W.mode = getMode();
        W.mix = 0; W.level = 0; W.userPulse = 0; W.face = null; W.ready = false;

        if (!W.renderer) {
            W.renderer = new THREE.WebGLRenderer({ canvas: canvas, alpha: true, antialias: true });
            W.renderer.setClearColor(0x000000, 0);
            W.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
        }
        W.scene = new THREE.Scene();
        W.camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 3000);
        W.root = new THREE.Group();
        W.scene.add(W.root);

        W.sphere = buildSphere();
        W.halo = buildHalo();
        W.root.add(W.sphere.group);
        W.root.add(W.halo.pts);

        if (W.mode === 'face') {
            W.shards = buildShards();
            W.root.add(W.shards.pts);
            if (typeof THREE.GLTFLoader !== 'undefined') {
                const myScene = W.scene;
                new THREE.GLTFLoader().load(WIRE.glbUrl, (gltf) => {
                    if (W.scene !== myScene) return;           // live mode was re-opened meanwhile
                    try {
                        W.face = buildFace(gltf);
                        W.root.add(W.face.group);
                    } catch (e) { console.warn('[NexuzWire] face build failed, showing orb:', e); }
                }, undefined, (err) => {
                    console.warn('[NexuzWire] could not load ' + WIRE.glbUrl + ' (put face.glb inside the static/ folder). Showing orb instead.', err);
                });
            } else {
                console.warn('[NexuzWire] THREE.GLTFLoader missing, showing orb instead.');
            }
        } else {
            W.shards = null;
        }

        if (!W.listenersAdded) {
            W.listenersAdded = true;
            window.addEventListener('resize', fitCamera);
        }
        styleForMode();
        fitCamera();
        W.ready = true;
    }

    function loop(now) {
        if (!isLive() || !W.ready) { resetStyle(); W.raf = 0; return; }
        W.raf = requestAnimationFrame(loop);
        try { animFrameId = W.raf; } catch (e) { /* binding not available */ }

        const t = now / 1000;
        const dt = Math.min(0.05, W.last ? t - W.last : 0.016);
        W.last = t;
        updateLevel(t, dt);

        const target = (W.mode === 'face' && W.face) ? 1 : 0;
        W.mix += (target - W.mix) * Math.min(1, dt * 1.8);
        const mix = W.mix, lvl = W.level;

        // orb (always built; fades out when the face takes over)
        const so = 1 - mix;
        W.sphere.group.visible = W.halo.pts.visible = so > 0.02;
        if (so > 0.02) {
            updateSphere(t, lvl);
            W.sphere.mat.opacity = (0.5 + 0.2 * lvl + 0.1) * so;
            W.halo.mat.opacity = 0.9 * so;
            W.sphere.group.scale.setScalar(1 + 0.25 * mix);
        }

        // face + shards
        if (W.face) {
            const vis = mix > 0.02;
            W.face.group.visible = vis;
            if (W.shards) W.shards.pts.visible = vis;
            if (vis) {
                updateFace(t, dt, lvl);
                const a = easeOut(W.face.assembly);
                W.face.lineMat.opacity = (0.35 + 0.65 * a) * mix;
                W.face.fillMat.opacity = 0.88 * a * mix;
                if (W.shards) {
                    updateShards(t, dt, lvl);
                    W.shards.mat.opacity = 0.85 * mix;
                }
            }
        }
        W.renderer.render(W.scene, W.camera);
    }

    function wireStart() {
        if (W.raf) cancelAnimationFrame(W.raf);
        W.last = 0;
        W.raf = requestAnimationFrame(loop);
    }

    // ---- re-point the two functions script.js already calls ----------------
    window.initThreeGlowVisualizer = function () {
        if (!WIRE.enabled || W.failed) return origInit.apply(this, arguments);
        try { wireInit(); }
        catch (e) {
            console.warn('[NexuzWire] WebGL setup failed, using the original visualizer:', e);
            W.failed = true;
            return origInit.apply(this, arguments);
        }
    };
    window.visualizeAudio = function () {
        if (!WIRE.enabled || W.failed) return origVis.apply(this, arguments);
        wireStart();
    };
})();
