/* Blocking <head> script: set color mode, then set data-themed img src before first fetch. */
(function () {
	var root = document.documentElement;
	var lightImageMissing = {};

	try {
		if (localStorage.getItem("colorMode") === "light") {
			root.classList.add("light-mode");
		}
	} catch (e) {}

	function resolveThemedSrc(logicalPath, shared) {
		if (!logicalPath) return logicalPath;
		var slash = logicalPath.lastIndexOf("/");
		if (slash === -1) return logicalPath;
		var dir = logicalPath.slice(0, slash + 1);
		var file = logicalPath.slice(slash + 1);
		var wantLight = !shared && root.classList.contains("light-mode");
		var lightSrc = dir + "light/" + file;
		if (wantLight && !lightImageMissing[logicalPath]) {
			return lightSrc;
		}
		return dir + "dark/" + file;
	}

	function oppositeThemedSrc(logicalPath) {
		var slash = logicalPath.lastIndexOf("/");
		if (slash === -1) return logicalPath;
		var dir = logicalPath.slice(0, slash + 1);
		var file = logicalPath.slice(slash + 1);
		var isLight = root.classList.contains("light-mode");
		return dir + (isLight ? "dark" : "light") + "/" + file;
	}

	function preload(url) {
		if (!url) return;
		var pre = new Image();
		pre.src = url;
	}

	function ensureErrorHandler(img, logicalPath, shared) {
		if (img.dataset.themeErrorBound || shared) return;
		img.dataset.themeErrorBound = "1";
		img.addEventListener("error", function () {
			var src = img.getAttribute("src") || "";
			if (src.indexOf("/light/") === -1) return;
			lightImageMissing[logicalPath] = true;
			img.setAttribute("src", resolveThemedSrc(logicalPath, true));
		});
	}

	function applyThemedImg(img, immediate) {
		var logical = img.getAttribute("data-themed");
		if (!logical) return;
		var shared = img.getAttribute("data-themed-shared") === "true";
		var next = resolveThemedSrc(logical, shared);
		var current = img.getAttribute("src") || "";
		ensureErrorHandler(img, logical, shared);

		if (current === next) {
			if (!shared) preload(oppositeThemedSrc(logical));
			return;
		}

		var token = String((parseInt(img.dataset.themeToken || "0", 10) || 0) + 1);
		img.dataset.themeToken = token;

		function commit() {
			if (img.dataset.themeToken !== token) return;
			if (resolveThemedSrc(logical, shared) !== next) return;
			img.setAttribute("src", next);
			if (!shared) preload(oppositeThemedSrc(logical));
		}

		/* First paint: set src now so the correct theme is the first request. */
		if (immediate || !current) {
			commit();
			return;
		}

		/* Toggle: keep current pixels until the next theme is decoded. */
		var pre = new Image();
		pre.onload = commit;
		pre.onerror = function () {
			if (img.dataset.themeToken !== token) return;
			if (!shared && next.indexOf("/light/") !== -1) {
				lightImageMissing[logical] = true;
				next = resolveThemedSrc(logical, true);
				img.setAttribute("src", next);
			}
		};
		pre.src = next;
		if (pre.complete && pre.naturalWidth) {
			commit();
		}
	}

	function applyAllThemedImages() {
		var imgs = document.querySelectorAll("img[data-themed]");
		for (var i = 0; i < imgs.length; i++) {
			/* false = wait for preload when swapping (no blank flash on toggle) */
			applyThemedImg(imgs[i], false);
		}
	}

	var mo = new MutationObserver(function (mutations) {
		for (var i = 0; i < mutations.length; i++) {
			var nodes = mutations[i].addedNodes;
			for (var j = 0; j < nodes.length; j++) {
				var n = nodes[j];
				if (n.nodeName === "IMG" && n.getAttribute && n.getAttribute("data-themed")) {
					applyThemedImg(n, true);
				} else if (n.querySelectorAll) {
					var imgs = n.querySelectorAll("img[data-themed]");
					for (var k = 0; k < imgs.length; k++) applyThemedImg(imgs[k], true);
				}
			}
		}
	});
	mo.observe(root, { childList: true, subtree: true });

	window.updateThemedImages = applyAllThemedImages;
	window.__themeImgMo = mo;
})();
