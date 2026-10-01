/* Minimal fake of the Leaflet API surface used by index.html, for offline logic testing only. */
(function () {
  "use strict";
  const BOUNDS = { latMin: 24.0, latMax: 45.9, lngMin: 122.5, lngMax: 146.5 };
  const COS_LAT = Math.cos((BOUNDS.latMin + BOUNDS.latMax) / 2 * Math.PI / 180);

  function makeFakeLayer() {
    return {
      _latlngs: null,
      addLayer(l) { (this._layers = this._layers || []).push(l); return this; },
      addTo(target) { if (target && target.addLayer) target.addLayer(this); return this; },
      bindTooltip() { return this; },
      setLatLngs(latlngs) { this._latlngs = latlngs; return this; },
      clearLayers() { this._layers = []; return this; }
    };
  }

  function fakeHandler(initiallyEnabled) {
    return {
      _enabled: !!initiallyEnabled,
      enable() { this._enabled = true; return this; },
      disable() { this._enabled = false; return this; },
      enabled() { return this._enabled; }
    };
  }

  const BASE_ZOOM = 5; // fitBounds()がリセットする基準ズーム（テスト用の固定値）

  function createMapObject(containerId, interactive) {
    const el = document.getElementById(containerId);
    // zoom はコンテナ中心を基準とした倍率、pan は中心のずれ(px)。
    // 実Leafletと同じ「pan/zoomすると同じ緯度経度が別の画面座標になる」性質だけを再現する。
    const state = { zoom: BASE_ZOOM, panX: 0, panY: 0 };

    function frame() {
      const rect = el.getBoundingClientRect();
      const pad = Math.min(rect.width, rect.height) * 0.06;
      const lngSpan = (BOUNDS.lngMax - BOUNDS.lngMin) * COS_LAT;
      const latSpan = (BOUNDS.latMax - BOUNDS.latMin);
      const scale = Math.min((rect.width - 2 * pad) / lngSpan, (rect.height - 2 * pad) / latSpan);
      return {
        rect, scale,
        offX: pad + ((rect.width - 2 * pad) - lngSpan * scale) / 2,
        offY: pad + ((rect.height - 2 * pad) - latSpan * scale) / 2,
        zoomScale: Math.pow(2, state.zoom - BASE_ZOOM)
      };
    }

    const map = {
      _el: el,
      _state: state,
      dragging: fakeHandler(interactive),
      scrollWheelZoom: fakeHandler(interactive),
      doubleClickZoom: fakeHandler(interactive),
      touchZoom: fakeHandler(interactive),
      boxZoom: fakeHandler(interactive),
      addLayer() { return this; },
      invalidateSize() { return this; },
      // bounds = [[minLat,minLng],[maxLat,maxLng]]。指定範囲が余白(padding)を残して
      // ちょうど収まるズーム・中心になるよう、実Leafletのfloor bounds-fittingを
      // 簡易に再現する（本物と同一のアルゴリズムではないが、「範囲が変われば
      // ズーム・中心も変わる」という、テストしたい性質は再現できる）。
      fitBounds(bounds, opts) {
        const pad = (opts && opts.padding) || [0, 0];
        const f = frame();
        const toBase = (lat, lng) => ({
          x: f.offX + (lng - BOUNDS.lngMin) * COS_LAT * f.scale,
          y: f.offY + (BOUNDS.latMax - lat) * f.scale
        });
        const p1 = toBase(bounds[0][0], bounds[0][1]);
        const p2 = toBase(bounds[1][0], bounds[1][1]);
        const spanX = Math.abs(p2.x - p1.x), spanY = Math.abs(p2.y - p1.y);
        const availW = Math.max(1, f.rect.width - 2 * pad[0]);
        const availH = Math.max(1, f.rect.height - 2 * pad[1]);
        const scaleX = spanX > 0 ? availW / spanX : Infinity;
        const scaleY = spanY > 0 ? availH / spanY : Infinity;
        let zoomScale = Math.min(scaleX, scaleY);
        if (!isFinite(zoomScale)) zoomScale = 1; // 面積ゼロ(単一点)のときは無変更
        const zoom = Math.max(4, Math.min(18, BASE_ZOOM + Math.log2(zoomScale)));
        state.zoom = zoom;
        zoomScale = Math.pow(2, zoom - BASE_ZOOM);
        const cx = f.rect.width / 2, cy = f.rect.height / 2;
        const centerBaseX = (p1.x + p2.x) / 2, centerBaseY = (p1.y + p2.y) / 2;
        state.panX = (centerBaseX - cx) * zoomScale;
        state.panY = (centerBaseY - cy) * zoomScale;
        return this;
      },
      getZoom() { return state.zoom; },
      setZoom(z) { state.zoom = z; return this; },
      getZoomScale(toZoom, fromZoom) { return Math.pow(2, toZoom - (fromZoom === undefined ? state.zoom : fromZoom)); },
      panBy(offset) {
        state.panX += offset[0];
        state.panY += offset[1];
        return this;
      },
      setZoomAround(point, zoom) {
        // point(画面座標)にある緯度経度が、ズーム後も同じ画面座標に来るようpanを調整する
        const anchor = map.containerPointToLatLng([point.x, point.y]);
        state.zoom = zoom;
        const after = map.latLngToContainerPoint([anchor.lat, anchor.lng]);
        state.panX += after.x - point.x;
        state.panY += after.y - point.y;
        return this;
      },
      latLngToContainerPoint(latlng) {
        const f = frame();
        const base = {
          x: f.offX + (latlng[1] - BOUNDS.lngMin) * COS_LAT * f.scale,
          y: f.offY + (BOUNDS.latMax - latlng[0]) * f.scale
        };
        const cx = f.rect.width / 2, cy = f.rect.height / 2;
        return {
          x: cx + (base.x - cx) * f.zoomScale - state.panX,
          y: cy + (base.y - cy) * f.zoomScale - state.panY
        };
      },
      containerPointToLatLng(pt) {
        const f = frame();
        const cx = f.rect.width / 2, cy = f.rect.height / 2;
        const baseX = cx + (pt[0] + state.panX - cx) / f.zoomScale;
        const baseY = cy + (pt[1] + state.panY - cy) / f.zoomScale;
        return {
          lat: BOUNDS.latMax - (baseY - f.offY) / f.scale,
          lng: BOUNDS.lngMin + (baseX - f.offX) / (COS_LAT * f.scale)
        };
      }
    };
    return map;
  }

  window.L = {
    map(containerId, opts) { return createMapObject(containerId, opts && opts.dragging); },
    tileLayer() { return makeFakeLayer(); },
    layerGroup() { return makeFakeLayer(); },
    circleMarker() { return makeFakeLayer(); },
    polyline() { return makeFakeLayer(); },
    point(x, y) { return { x, y }; }
  };
})();
