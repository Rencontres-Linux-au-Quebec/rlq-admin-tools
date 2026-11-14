/*
 * link-page.js - script of the link pages of nginx-link-page.sh (PAGE_n_SCRIPT=yes, the default).
 * Copyright (C) 2026 Services-Conseils Linux Inc. - AGPL-3.0-or-later (see LICENSE).
 * Copied as js/link-page.js into each page folder and loaded from the page's own server only (Content-Security-Policy
 * script-src 'self'). Every page stays complete without it: the "Theme" menu then opens the theme-NAME.html pages.
 *   - theme: applied in place (class of <html>, icons, browser bar colour) and remembered in the browser (localStorage)
 *   - language: the language chosen with the language link is remembered and reopened on the next visit
 *   - "Share" button: share sheet of the phone (navigator.share) or copy of the address (navigator.clipboard)
 *   - themes one after the other (PAGE_n_THEME=all, 1.54, data-rotate="SECONDS"): every theme of the "Theme" button in turn, so
 *     the visitors see them all; a button at the bottom left stops and starts it; a theme chosen in the menu stops it (and is
 *     remembered as usual); a hidden tab skips the turns; with "reduce motion", it starts stopped; a remembered theme wins
 *   - greeting (PAGE_n_GREETING=yes, 1.53): asks Odoo on the same site (data-lp-me, route /rlq/session/me of the module
 *     rlq_session_check) who is signed in: "Bonjour Marie"; for the members of the group chosen in Odoo, a button at the bottom
 *     right shows the name, address, e-mail, phone and groups. Nothing personal is written in the page: everything comes from that
 *     answer, put in the page as text only (never as HTML), and nothing is kept in the browser.
 * No cookie of its own, nothing sent to the server but that question. Data come from attributes written by nginx-link-page.sh:
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
		salutation();
		defilement();
	});

	// 1.54: PAGE_n_THEME=all: the themes of the "Theme" button one after the other, every data-rotate seconds
	function defilement() {
		var secondes = parseInt(racine.getAttribute("data-rotate") || "0", 10);
		var noms = Object.keys(themes);
		if (!(secondes >= 3) || noms.length < 2 || lire(cleTheme)) { return; }   // a theme chosen before: kept
		var en = (racine.getAttribute("lang") || "").slice(0, 2) === "en";
		var minuterie = null;
		var bouton = element("button", "rotate-button");
		bouton.type = "button";
		function nomTheme(t) {
			var a = document.querySelector('.theme-menu a[data-theme="' + t + '"]');
			return a ? a.textContent.replace(/^\s+|\s+$/g, "") : t;
		}
		function etiquette() {
			var arret = minuterie !== null;
			bouton.textContent = (arret ? "\u23F8 " : "\u25B6 ") + nomTheme(themeActif);
			bouton.setAttribute("aria-pressed", arret ? "true" : "false");
			bouton.title = arret ? (en ? "Stop the themes" : "Arrêter le défilement des thèmes") : (en ? "Show the themes one after the other" : "Faire défiler les thèmes");
		}
		function suivant() {
			if (document.hidden) { return; }
			var i = noms.indexOf(themeActif);
			appliquer(noms[(i + 1) % noms.length]);
			etiquette();
		}
		function demarrer() { if (minuterie === null) { minuterie = window.setInterval(suivant, secondes * 1000); } etiquette(); }
		function arreter() { if (minuterie !== null) { window.clearInterval(minuterie); minuterie = null; } etiquette(); }
		bouton.addEventListener("click", function () { if (minuterie === null) { suivant(); demarrer(); } else { arreter(); } });
		Array.prototype.forEach.call(document.querySelectorAll(".theme-menu a[data-theme]"), function (a) {
			a.addEventListener("click", arreter);                     // the visitor chose: no more turns
		});
		document.body.appendChild(bouton);
		var calme = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
		if (calme) { etiquette(); } else { demarrer(); }
	}

	// 1.53: "Bonjour Prénom" and the profile button, for a person signed in to Odoo
	function element(nom, classe, texte) {
		var e = document.createElement(nom);
		if (classe) { e.className = classe; }
		if (texte) { e.textContent = texte; }           // text only: never HTML from the answer
		return e;
	}
	function salutation() {
		var salut = document.querySelector("[data-lp-me]");
		if (!salut || typeof window.fetch !== "function") { return; }
		var en = (racine.getAttribute("lang") || "").slice(0, 2) === "en";
		window.fetch(salut.getAttribute("data-lp-me"), { credentials: "same-origin", cache: "no-store", headers: { "Accept": "application/json" } })
			.then(function (r) { return r.ok ? r.json() : null; })
			.then(function (d) {
				if (!d || d.signed_in !== true || typeof d.first_name !== "string" || !d.first_name) { return; }
				salut.textContent = (en ? "Hello " : "Bonjour ") + d.first_name;
				salut.hidden = false;
				if (d.details && typeof d.details === "object") { profil(d.details, en); }
			})
			.catch(function () { /* Odoo not reachable: the page stays as it is */ });
	}
	function profil(d, en) {
		var bouton = element("button", "lp-me-button");
		bouton.type = "button";
		bouton.setAttribute("aria-expanded", "false");
		bouton.setAttribute("aria-controls", "lp-me-panel");
		bouton.setAttribute("aria-label", en ? "My profile" : "Mon profil");
		bouton.title = en ? "My profile" : "Mon profil";
		bouton.textContent = "\uD83D\uDC64";               // bust in silhouette
		var panneau = element("section", "lp-me-panel");
		panneau.id = "lp-me-panel";
		panneau.hidden = true;
		panneau.setAttribute("aria-label", en ? "My profile" : "Mon profil");
		var fermer = element("button", "lp-me-close", "\u00D7");
		fermer.type = "button";
		fermer.setAttribute("aria-label", en ? "Close" : "Fermer");
		panneau.appendChild(fermer);
		if (typeof d.name === "string" && d.name) { panneau.appendChild(element("h2", "", d.name)); }
		if (Array.isArray(d.address) && d.address.length) {
			var adresse = element("p", "lp-me-address");
			d.address.forEach(function (ligne, i) {
				if (i) { adresse.appendChild(document.createElement("br")); }
				adresse.appendChild(document.createTextNode(String(ligne)));
			});
			panneau.appendChild(adresse);
		}
		if (typeof d.email === "string" && d.email) { panneau.appendChild(element("p", "", d.email)); }
		if (typeof d.phone === "string" && d.phone) { panneau.appendChild(element("p", "", d.phone)); }
		if (Array.isArray(d.groups) && d.groups.length) {
			panneau.appendChild(element("h3", "", en ? "Groups" : "Groupes"));
			var liste = element("ul", "lp-me-groups");
			d.groups.forEach(function (g) { liste.appendChild(element("li", "", String(g))); });
			panneau.appendChild(liste);
		}
		function basculer(ouvrir) {
			panneau.hidden = !ouvrir;
			bouton.setAttribute("aria-expanded", ouvrir ? "true" : "false");
			if (ouvrir) { fermer.focus(); } else { bouton.focus(); }
		}
		bouton.addEventListener("click", function () { basculer(panneau.hidden); });
		fermer.addEventListener("click", function () { basculer(false); });
		document.addEventListener("keydown", function (ev) { if (ev.key === "Escape" && !panneau.hidden) { basculer(false); } });
		document.body.appendChild(panneau);
		document.body.appendChild(bouton);
	}
}());
