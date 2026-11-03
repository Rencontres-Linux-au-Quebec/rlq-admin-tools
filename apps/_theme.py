#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
# _theme.py - color themes of the programs (shared module, apps/): --theme N, THEME=N in a configuration file.
#
"""Color themes (thèmes de couleurs) : --theme N choisit une palette lisible sur le fond du terminal.

  0  automatic: the colors of the terminal (nothing changes; default)
  1  dark background        2  light background
  3  dark background, high contrast        4  light background, high contrast

Every program keeps writing its usual SGR codes (1;33 for yellow, 7;91 for a red reverse video...). With a theme above 0 each code goes through sgr(): the
colors are read as RGB (standard xterm values), then replaced by the NEAREST color of the 256-color palette whose contrast with the background of the
theme reaches the minimum of the theme (WCAG ratio: 4.5 for the themes 1 and 2, 7 for the themes 3 and 4). A reverse video (7) becomes an explicit
background and text (the terminal does not decide any more), the faint attribute (2) becomes a gray that reads, a background gets a text of its own.
The references of the backgrounds are the worst plausible ones (#262626 for a dark terminal, #eeeeee for a light one): a pure black or pure white
background reads even better. Theme 0 returns the code as it is. Nothing is sent to the terminal here: only the text of the codes is computed.

The theme is chosen, by priority: --theme, THEME of the configuration file of the program, THEME of /etc/default/app-default.conf (or ~/.app-default.conf),
the environment variable NGINX_TOOLS_THEME (which each program exports for the programs it starts), 0.

Command line (the programs of bash use it):
  python3 apps/_theme.py --demo [N]     the colors of the theme N (or of all), drawn on the reference background of the theme: judge them by eye
  python3 apps/_theme.py --bash N       shell assignments THEME_SGR_RED=... for the colors that the bash programs use
  python3 apps/_theme.py --sgr N CODE   the code CODE (for example 1;33) as the theme N shows it
"""
import functools
import os
import sys

__version__ = "1.0.20261103.112517"

ENV_VARIABLE = "NGINX_TOOLS_THEME"
# number -> (name in French, name in English, reference background, default text, minimum contrast); theme 0 has no reference
THEMES = {
    0: ("automatique (couleurs du terminal)", "automatic (terminal colors)", None, None, 0.0),
    1: ("fond sombre", "dark background", (38, 38, 38), (229, 229, 229), 4.5),
    2: ("fond clair", "light background", (238, 238, 238), (28, 28, 28), 4.5),
    3: ("fond sombre, contraste élevé", "dark background, high contrast", (38, 38, 38), (255, 255, 255), 7.0),
    4: ("fond clair, contraste élevé", "light background, high contrast", (238, 238, 238), (0, 0, 0), 7.0),
}

# Standard xterm colors (the codes 30 to 37 and 90 to 97 depend on the terminal; these are the usual values)
STANDARD = [(0, 0, 0), (205, 0, 0), (0, 205, 0), (205, 205, 0), (0, 0, 238), (205, 0, 205), (0, 205, 205), (229, 229, 229)]
BRIGHT = [(127, 127, 127), (255, 0, 0), (0, 255, 0), (255, 255, 0), (92, 92, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255)]
CUBE = (0, 95, 135, 175, 215, 255)


def indexed_rgb(n):
    """RGB of the color n (0 to 255) of the 256-color palette."""
    if n < 8:
        return STANDARD[n]
    if n < 16:
        return BRIGHT[n - 8]
    if n < 232:
        n -= 16
        return (CUBE[n // 36], CUBE[(n // 6) % 6], CUBE[n % 6])
    level = 8 + 10 * (n - 232)
    return (level, level, level)


# Candidates of a replacement: the cube and the grays (0 to 15 are left to the terminal, which draws them as it likes)
CANDIDATES = tuple((n, indexed_rgb(n)) for n in range(16, 256))


def _linear(channel):
    c = channel / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb):
    return 0.2126 * _linear(rgb[0]) + 0.7152 * _linear(rgb[1]) + 0.0722 * _linear(rgb[2])


def contrast(first, second):
    """WCAG contrast ratio (1 to 21) between two RGB colors."""
    a, b = luminance(first), luminance(second)
    if a < b:
        a, b = b, a
    return (a + 0.05) / (b + 0.05)


def _distance(first, second):
    mean_red = (first[0] + second[0]) / 2.0
    return ((2 + mean_red / 256.0) * (first[0] - second[0]) ** 2 + 4 * (first[1] - second[1]) ** 2
            + (2 + (255 - mean_red) / 256.0) * (first[2] - second[2]) ** 2)


def _nearest(rgb, accept):
    """(index, rgb) of the candidate nearest to rgb that accept() agrees with; None if no candidate does."""
    best, best_distance = None, None
    for n, value in CANDIDATES:
        if not accept(value):
            continue
        d = _distance(rgb, value)
        if best_distance is None or d < best_distance:
            best, best_distance = (n, value), d
    return best


def parse_theme(value):
    """The theme number from a text (an option, a configuration value): 0 to 4. ValueError for anything else."""
    text = str(value).strip()
    if not text.isdigit() or int(text) not in THEMES:
        raise ValueError(f"theme must be one of {', '.join(str(n) for n in sorted(THEMES))} (received: {value!r})")
    return int(text)


def _parse_sgr(code):
    """(attributes, fg, bg) of an SGR parameter text: attributes = set of the codes that are neither colors nor a reset; fg and bg = RGB or None."""
    values = [int(p) for p in str(code).split(";") if p.strip().isdigit()]
    attributes, fg, bg = [], None, None
    i = 0
    while i < len(values):
        v = values[i]
        if v in (38, 48) and i + 1 < len(values):
            if values[i + 1] == 5 and i + 2 < len(values):
                color = indexed_rgb(min(values[i + 2], 255))
                i += 3
            elif values[i + 1] == 2 and i + 4 < len(values):
                color = tuple(min(c, 255) for c in values[i + 2:i + 5])
                i += 5
            else:
                i += 1
                continue
            if v == 38:
                fg = color
            else:
                bg = color
            continue
        if 30 <= v <= 37:
            fg = STANDARD[v - 30]
        elif 90 <= v <= 97:
            fg = BRIGHT[v - 90]
        elif 40 <= v <= 47:
            bg = STANDARD[v - 40]
        elif 100 <= v <= 107:
            bg = BRIGHT[v - 100]
        elif v == 39:
            fg = None
        elif v == 49:
            bg = None
        else:
            attributes.append(v)
        i += 1
    return attributes, fg, bg


@functools.lru_cache(maxsize=None)
def resolve(code, number):
    """(text of the code, text color, background color) as the theme `number` shows the SGR code `code`. The colors are RGB tuples or None (terminal default)."""
    if number == 0 or not code:
        attributes, fg, bg = _parse_sgr(code)
        return code, fg, bg
    _, _, theme_bg, theme_fg, minimum = THEMES[number]
    attributes, fg, bg = _parse_sgr(code)
    reverse = 7 in attributes
    attributes = [a for a in attributes if a not in (7, 0)]
    dim = 2 in attributes
    attributes = [a for a in attributes if a != 2]
    derived = False                                                # text color not written by the program: black or white, whichever reads best
    if reverse:
        if fg is None and bg is None:
            return code, None, None                                # reverse of the default colors: the terminal swaps its own, nothing to compute
        derived = bg is None
        fg, bg = (bg if bg is not None else theme_bg), (fg if fg is not None else theme_fg)
    bg_index = None
    if bg is not None:
        # a background becomes a color of the palette that a black or white text can read; otherwise it moves to the nearest one that does
        reads = lambda c: max(contrast(c, (0, 0, 0)), contrast(c, (255, 255, 255))) >= minimum
        bg_index, bg = _nearest(bg, reads) if not reads(_nearest(bg, lambda c: True)[1]) else _nearest(bg, lambda c: True)
        background = bg
    else:
        background = theme_bg
    if fg is None and dim:
        fg = tuple((a + b) // 2 for a, b in zip(theme_fg, theme_bg))        # faint text: halfway between the text and the background, then made to read
    if (fg is None and bg is not None) or (derived and bg is not None):
        fg = (0, 0, 0) if contrast(bg, (0, 0, 0)) >= contrast(bg, (255, 255, 255)) else (255, 255, 255)
    fg_index = None
    if fg is not None:
        found = _nearest(fg, lambda c: contrast(c, background) >= minimum)
        if found is None:
            found = (16, (0, 0, 0)) if contrast((0, 0, 0), background) >= contrast((255, 255, 255), background) else (231, (255, 255, 255))
        fg_index, fg = found
    parts = [str(a) for a in attributes]
    if fg_index is not None:
        parts.append(f"38;5;{fg_index}")
    if bg_index is not None:
        parts.append(f"48;5;{bg_index}")
    return ";".join(parts), fg, bg


_current = None


def current():
    """The theme in use: set_theme(), else the environment variable, else 0."""
    global _current
    if _current is None:
        try:
            _current = parse_theme(os.environ.get(ENV_VARIABLE, "0") or "0")
        except ValueError:
            _current = 0
    return _current


def set_theme(value):
    """Chooses the theme (a number or a text) and exports it for the programs that this one starts. ValueError if it does not exist."""
    global _current
    _current = parse_theme(value)
    os.environ[ENV_VARIABLE] = str(_current)
    return _current


def sgr(code):
    """The SGR code `code` as the current theme shows it (theme 0: unchanged)."""
    number = current()
    if number == 0 or not code:
        return code
    return resolve(code, number)[0]


def name(number, language="en"):
    return THEMES[number][0 if language.startswith("fr") else 1]


def description(language="en"):
    """One line for the help of --theme."""
    return "; ".join(f"{n} = {name(n, language)}" for n in sorted(THEMES))


# Colors that the bash programs use: variable -> SGR code (their C_RED, C_YELLOW... are built from these)
BASH_COLORS = {"RED": "1;31", "YELLOW": "1;33", "GREEN": "1;32", "CYAN": "1;36", "MAL": "1;35", "BOLD": "1", "DIM": "2"}


def bash_assignments(number):
    """Shell lines THEME_SGR_RED='...' for the theme `number` (nothing to change for the theme 0)."""
    return "\n".join(f"THEME_SGR_{key}='{resolve(code, number)[0]}'" for key, code in BASH_COLORS.items())


# Codes that the programs write, for the demonstration (text shown for each)
DEMO_CODES = [("1;31", "error / erreur"), ("1;32", "OK"), ("1;33", "warning / avertissement"), ("1;35", "malicious / malveillant"), ("1;36", "title / titre"),
              ("36", "server / serveur"), ("33", "organization / organisation"), ("32", "normal"), ("90", "address / adresse"), ("2", "faint / discret"),
              ("1;91", "banned / banni"), ("1;93", "robot refused / robot refusé"), ("7;35", "suspect request / requête suspecte"),
              ("7;91", "5xx error / erreur 5xx"), ("7;93", "4xx error / erreur 4xx"), ("7;31", "account form / formulaire de compte"),
              ("107;30", "whitelist / liste blanche"), ("1;97;44", "connection / connexion"), ("30;46", "highlight / mot surligné"),
              ("1;97;41", "recording / enregistrement")]


def demo_lines(number, language="en"):
    """The colors of the theme `number`, each row drawn on the reference background of the theme (so the preview is right on any terminal)."""
    title = f"--theme {number}: {name(number, language)}"
    if number == 0:
        return [title, "  " + ("rien ne change : les couleurs du terminal" if language.startswith("fr") else "nothing changes: the terminal's own colors")]
    _, _, bg, fg, minimum = THEMES[number]
    ground = f"48;5;{_nearest(bg, lambda c: True)[0]}"
    lines = [f"\x1b[0m{title} ({'contraste minimal' if language.startswith('fr') else 'minimum contrast'} {minimum:g})"]
    for code, label in DEMO_CODES:
        mapped, fore, back = resolve(code, number)
        effective_bg = back if back is not None else bg
        shown = mapped if fore is not None else code
        ratio = contrast(fore, effective_bg) if fore is not None else 0.0
        lines.append(f"  \x1b[{ground}m \x1b[0m\x1b[{ground}m\x1b[{shown}m {label:<40}\x1b[0m\x1b[{ground}m \x1b[0m  {code:<10} -> {mapped:<22} {ratio:4.1f}")
    return lines


def _main(argv):
    language = "fr" if (os.environ.get("LC_ALL") or os.environ.get("LANG") or "").lower().startswith("fr") else "en"
    if len(argv) >= 2 and argv[1] == "--demo":
        numbers = [parse_theme(argv[2])] if len(argv) > 2 else sorted(THEMES)
        for number in numbers:
            print("\n".join(demo_lines(number, language)))
        return 0
    if len(argv) == 3 and argv[1] == "--bash":
        number = parse_theme(argv[2])
        if number:
            print(bash_assignments(number))
        return 0
    if len(argv) == 4 and argv[1] == "--sgr":
        print(resolve(argv[3], parse_theme(argv[2]))[0])
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
