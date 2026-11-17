"""Colour helpers: find the dominant colour of a cover image and turn it into UI accent colours."""
import colorsys


def hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    r, g, b = (max(0, min(255, int(round(c)))) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def mix(a, b, t):
    """Blend two (r, g, b) colours: t=0 gives a, t=1 gives b."""
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def luminance(rgb):
    r, g, b = (c / 255 for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def readable_text(background_hex):
    """Black or white, whichever is easier to read on this background."""
    return "#000000" if luminance(hex_to_rgb(background_hex)) > 0.5 else "#FFFFFF"


def dominant_color(img):
    """The most 'characteristic' colour of a PIL image as (r, g, b), or None if it can't be worked out.
    Prefers colours that are common, saturated and neither too dark nor too light, so a cover that is
    mostly black with a red logo gives red rather than black."""
    try:
        small = img.convert("RGB").resize((64, 64))
        quant = small.quantize(colors=8)
        palette = quant.getpalette()
        counts = quant.getcolors() or []
        total = sum(c for c, _ in counts) or 1
        best, best_score, fallback, fallback_count = None, 0.0, None, -1
        for count, idx in counts:
            rgb = tuple(palette[idx * 3: idx * 3 + 3])
            if len(rgb) < 3:
                continue
            if count > fallback_count:
                fallback, fallback_count = rgb, count
            h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
            if v < 0.15:
                continue                                    # basically black
            score = ((count / total) ** 0.5) * (s + 0.12) * (1.0 - abs(v - 0.7))
            if score > best_score:
                best, best_score = rgb, score
        return tuple(best or fallback) if (best or fallback) else None
    except Exception:
        return None


def make_accent(rgb, dark_ui=True):
    """(accent_hex, hover_hex) for a UI accent based on this colour, adjusted so it stays visible:
    brighter on dark themes, darker on the light theme, and never washed out."""
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    if s > 0.12:
        s = max(s, 0.45)
    v = min(max(v, 0.70), 0.95) if dark_ui else min(max(v, 0.35), 0.60)
    accent = tuple(c * 255 for c in colorsys.hsv_to_rgb(h, s, v))
    hover = tuple(c * 255 for c in colorsys.hsv_to_rgb(h, s, v * 0.85))
    return rgb_to_hex(accent), rgb_to_hex(hover)
