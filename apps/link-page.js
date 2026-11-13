/*
 * link-page.js - script of the link pages of nginx-link-page.sh (PAGE_n_SCRIPT=yes, the default).
 * Copyright (C) 2026 Services-Conseils Linux Inc. - AGPL-3.0-or-later (see LICENSE).
 * Copied as js/link-page.js into each page folder and loaded from the page's own server only (Content-Security-Policy
 * script-src 'self'). Every page stays complete without it: the "Theme" menu then opens the theme-NAME.html pages.
 *   - theme: applied in place (class of <html>, icons, browser bar colour) and remembered in the browser (localStorage)
 *   - language: the language chosen with the language link is remembered and reopened on the next visit
 *   - "Share" button: share sheet of the phone (navigator.share) or copy of the address (navigator.clipboard)
 * No cookie, nothing sent to the server. Data come from attributes written by nginx-link-page.sh:
 *   <html data-page="/liens/" data-themes="NAME|BASE|COLOUR ..." data-other-lang="en" data-other-href="/liens/en/">
 */
(function () {
	"use strict";
	var racine = document.documentElement;
	var page = racine.getAttribute("data-page") || "/";
	var cleTheme = "nginx-link-page:" + page + ":theme";
	var cleLangue = "nginx-link-page:" + page + ":lang";

	function lire(cle) {
		try { return window.localStorage.getItem(cle); } catch (e) { return null; }
	}
	function ecrire(cle, valeur) {
		try { window.localStorage.setItem(cle, valeur); } catch (e) { /* private browsing or storage disabled: not remembered */ }
	}

	// 1) remembered language: go to it before anything is drawn
	var autreLangue = racine.getAttribute("data-other-lang");
	var autreHref = racine.getAttribute("data-other-href");
	if (autreLangue && autreHref && lire(cleLangue) === autreLangue) {
		window.location.replace(autreHref);
		return;
	}

	// 2) themes offered by the page: NAME|BASE|COLOUR separated by spaces (BASE: light, dark or auto; COLOUR may be empty)
	var themes = {};
	(racine.getAttribute("data-themes") || "").split(/\s+/).forEach(function (entree) {
		var champs = entree.split("|");
		if (champs[0]) { themes[champs[0]] = { base: champs[1] || "auto", couleur: champs[2] || "" }; }
	});
	var themePage = (racine.className.match(/(?:^|\s)theme-(\S+)/) || [])[1] || "auto";
	var themeActif = themePage;

	function classe(theme) {
		racine.className = racine.className.replace(/(^|\s)theme-\S+/g, "").replace(/^\s+|\s+$/g, "");
		racine.classList.add("theme-" + theme);
	}
	// the class is set at once (the script is in <head>): no flash of the default theme
	var memorise = lire(cleTheme);
	if (memorise && themes[memorise] && memorise !== themePage) {
		classe(memorise);
		themeActif = memorise;
	}

	function barre(theme) {   // <meta name="theme-color">: colour of the browser bar on phones
		var d = themes[theme];
		var tete = document.head;
		Array.prototype.forEach.call(document.querySelectorAll('meta[name="theme-color"]'), function (m) { m.parentNode.removeChild(m); });
		function ajouter(couleur, media) {
			var m = document.createElement("meta");
			m.setAttribute("name", "theme-color");
			m.setAttribute("content", couleur);
			if (media) { m.setAttribute("media", media); }
			tete.appendChild(m);
		}
		if (d.couleur) { ajouter(d.couleur); }
		else if (d.base === "dark") { ajouter("#121212"); }
		else if (d.base === "light") { ajouter("#ffffff"); }
		else { ajouter("#ffffff", "(prefers-color-scheme: light)"); ajouter("#121212", "(prefers-color-scheme: dark)"); }
	}

	function icones(theme) {   // LINK_n_ICON_DARK: <source data-icon-dark> used always, never or as the system says
		var base = themes[theme].base;
		var media = base === "dark" ? "all" : (base === "light" ? "not all" : "(prefers-color-scheme: dark)");
		Array.prototype.forEach.call(document.querySelectorAll("source[data-icon-dark]"), function (s) { s.setAttribute("media", media); });
	}

	function menu(theme) {   // current theme marked in the menu
		Array.prototype.forEach.call(document.querySelectorAll(".theme-menu a[data-theme]"), function (a) {
			if (a.getAttribute("data-theme") === theme) { a.setAttribute("aria-current", "page"); }
			else { a.removeAttribute("aria-current"); }
		});
	}

	function appliquer(theme) {
		classe(theme);
		themeActif = theme;
		barre(theme);
		icones(theme);
		menu(theme);
	}

	function partage() {
		var bouton = document.querySelector(".share-button");
		if (!bouton) { return; }
		var peutPartager = typeof navigator.share === "function";
		var peutCopier = navigator.clipboard && typeof navigator.clipboard.writeText === "function";
		if (!peutPartager && !peutCopier) { return; }   // stays hidden
		var libelle = bouton.textContent;
		var adresse = bouton.getAttribute("data-url") || window.location.href.replace(/[?#].*$/, "").replace(/[^\/]*\.html$/, "");
		bouton.hidden = false;
		bouton.addEventListener("click", function () {
			if (peutPartager) {
				navigator.share({ title: document.title, url: adresse }).catch(function () { /* closed by the visitor */ });
				return;
			}
			navigator.clipboard.writeText(adresse).then(function () {
				bouton.textContent = bouton.getAttribute("data-done") || libelle;
				window.setTimeout(function () { bouton.textContent = libelle; }, 2000);
			}, function () { /* copy refused: nothing to do */ });
		});
	}

	document.addEventListener("DOMContentLoaded", function () {
		if (themes[themeActif]) {
			if (themeActif !== themePage) { barre(themeActif); icones(themeActif); }
			menu(themeActif);
		}
		// theme chosen in the menu: applied in place and remembered; the link to theme-NAME.html is only the no-script fallback
		Array.prototype.forEach.call(document.querySelectorAll(".theme-menu a[data-theme]"), function (a) {
			a.addEventListener("click", function (ev) {
				var theme = a.getAttribute("data-theme");
				if (!themes[theme]) { return; }
				ev.preventDefault();
				appliquer(theme);
				ecrire(cleTheme, theme);
				var details = a.closest("details");
				if (details) { details.open = false; }
			});
		});
		// language chosen with the language link: remembered for the next visit
		Array.prototype.forEach.call(document.querySelectorAll("a[data-lang]"), function (a) {
			a.addEventListener("click", function () { ecrire(cleLangue, a.getAttribute("data-lang")); });
		});
		partage();
	});
}());
