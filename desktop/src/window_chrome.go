package main

// desktopDragRegionClass must stay in sync with dashboard DESKTOP_DRAG_REGION_CLASS.
// Frameless moving uses CSS `--wails-draggable: drag` plus this injected starter:
// the remote dashboard origin never loads Wails `/wails/runtime.js`.
// Frameless edge/corner resizing rides on the same starter, mirroring the Wails
// runtime's own strategy: pure edge detection, `wails:resize:<edge>` messages,
// no overlay elements, scrollbar width excluded from the right/bottom strips.
// clientY <= 32 must match dashboard DESKTOP_TITLEBAR_DRAG_HEIGHT.
const desktopDragRegionClass = "octop-desktop-drag"

func dragOverlayJS() string {
	return `(function(){
		if (!document.body || !window._wails || typeof window._wails.invoke !== 'function') return;
		if (document.documentElement.dataset.octopDragReady === '1') return;
		document.documentElement.dataset.octopDragReady = '1';
		var armed = false, startX = 0, startY = 0;
		var resizeEdge = '', resizeArmed = false;
		var noDrag = 'button, a, input, textarea, select, [role="button"], [role="menuitem"], [data-octop-no-drag], .octop-desktop-no-drag';
		function targetEl(t) {
			if (t && t.nodeType === 1) return t;
			return t && t.parentElement ? t.parentElement : null;
		}
		function shouldArm(event) {
			if (event.button !== 0) return false;
			if (resizeEdge) return false;
			var el = targetEl(event.target);
			if (!el || !el.closest) return false;
			if (el.closest(noDrag)) return false;
			var value = window.getComputedStyle(el).getPropertyValue('--wails-draggable').trim();
			if (value === 'no-drag') return false;
			if (value === 'drag') return true;
			return event.clientY <= 32;
		}
		window.addEventListener('mousedown', function(event) {
			if (!shouldArm(event)) return;
			armed = true;
			startX = event.screenX;
			startY = event.screenY;
		}, true);
		window.addEventListener('mousemove', function(event) {
			if (!armed) return;
			if (Math.abs(event.screenX - startX) < 3 && Math.abs(event.screenY - startY) < 3) return;
			armed = false;
			window._wails.invoke('wails:drag');
		}, true);
		window.addEventListener('mouseup', function() { armed = false; }, true);
		window.addEventListener('dblclick', function(event) {
			if (!shouldArm(event)) return;
			window._wails.invoke('wails:drag:doubleclick');
		}, true);
		// Message keys and cursor styles must be kept apart: the Go-side maps
		// (Windows edgeMap / Linux gdkEdgeForBorder) only accept the Wails
		// runtime's single-corner keys ('n-resize'...'nw-resize'); CSS two-corner
		// cursor values ('ns-resize' etc.) never hit the map, killing resize in
		// every direction (broken ever since #1657).
		var edgeKeys = { n: 'n-resize', s: 's-resize', e: 'e-resize', w: 'w-resize', ne: 'ne-resize', nw: 'nw-resize', se: 'se-resize', sw: 'sw-resize' };
		var edgeCursors = { n: 'ns-resize', s: 'ns-resize', e: 'ew-resize', w: 'ew-resize', ne: 'nesw-resize', nw: 'nwse-resize', se: 'nwse-resize', sw: 'nesw-resize' };
		function edgeAt(event) {
			var edge = 5, corner = 12;
			var right = window.innerWidth - Math.max(0, window.innerWidth - document.documentElement.clientWidth);
			var bottom = window.innerHeight - Math.max(0, window.innerHeight - document.documentElement.clientHeight);
			var l = event.clientX <= edge, r = event.clientX >= right - edge;
			var t = event.clientY <= edge, b = event.clientY >= bottom - edge;
			var lc = event.clientX <= corner, rc = event.clientX >= right - corner;
			var tc = event.clientY <= corner, bc = event.clientY >= bottom - corner;
			if (tc && lc) return 'nw';
			if (tc && rc) return 'ne';
			if (bc && lc) return 'sw';
			if (bc && rc) return 'se';
			if (l) return 'w';
			if (r) return 'e';
			if (t) return 'n';
			if (b) return 's';
			return '';
		}
		window.addEventListener('mousedown', function(event) {
			if (event.button === 0 && resizeEdge) resizeArmed = true;
		}, true);
		window.addEventListener('mousemove', function(event) {
			if (resizeArmed) {
				resizeArmed = false;
				window._wails.invoke('wails:resize:' + edgeKeys[resizeEdge]);
				return;
			}
			var edge = edgeAt(event);
			if (edge !== resizeEdge) {
				resizeEdge = edge;
				document.body.style.cursor = edge ? edgeCursors[edge] : '';
			}
		}, true);
		window.addEventListener('mouseup', function() { resizeArmed = false; }, true);
	})();`
}
