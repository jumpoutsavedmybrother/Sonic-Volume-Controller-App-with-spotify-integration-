"""Colour themes. To add one: add an entry to THEMES and its name to THEME_ORDER."""

KEY_COLOR = "#000001"            # colour-keyed pixels are see-through; in the glass theme they show the blur
GLASS_USE_NATIVE_BLUR = True     # set False to always use the solid "frosted" look instead of real blur

THEME_ORDER = ["green", "purple", "red", "grey", "black", "white", "glass"]

THEMES = {
    "green": { #green theme
        "mode": "dark", "bg_dark": "#0D0D0D", "panel_bg": "#141414", "scroll_bg": "#000000",
        "accent": "#1DB954", "hover": "#1AA34A", "text": "white", "subtext": "gray60",
        "button_bg": "#262626", "button_hover": "#3D3D3D"
    },
    "purple": { #purple theme
        "mode": "dark", "bg_dark": "#0D0D0D", "panel_bg": "#141414", "scroll_bg": "#000000",
        "accent": "#9333EA", "hover": "#7E22CE", "text": "white", "subtext": "gray60",
        "button_bg": "#262626", "button_hover": "#3D3D3D"
    },
    "red": { #red theme
        "mode": "dark", "bg_dark": "#0D0D0D", "panel_bg": "#141414", "scroll_bg": "#000000",
        "accent": "#E50914", "hover": "#B80710", "text": "white", "subtext": "gray60",
        "button_bg": "#262626", "button_hover": "#3D3D3D"
    },
    "grey": { #grey theme
        "mode": "dark", "bg_dark": "#121212", "panel_bg": "#1E1E1E", "scroll_bg": "#000000",
        "accent": "#9E9E9E", "hover": "#757575", "text": "white", "subtext": "gray60",
        "button_bg": "#2C2C2C", "button_hover": "#3D3D3D"
    },
    "black": { #black theme
        "mode": "dark", "bg_dark": "#050505", "panel_bg": "#0F0F0F", "scroll_bg": "#000000",
        "accent": "#FFFFFF", "hover": "#E5E5E5", "text": "white", "subtext": "gray60",
        "button_bg": "#222222", "button_hover": "#333333"
    },
    "white": { #white theme
        "mode": "light", "bg_dark": "#F3F4F6", "panel_bg": "#FFFFFF", "scroll_bg": "#FAFAFA",
        "accent": "#111827", "hover": "#374151", "text": "#111827", "subtext": "#6B7280",
        "button_bg": "#E5E7EB", "button_hover": "#D1D5DB"
    },
    "glass": { #liquid-glass theme: blurred see-through window, hairline rim borders, frosted pill buttons
        "glass": True, "mode": "dark",
        "bg_dark": KEY_COLOR, "panel_bg": KEY_COLOR, "scroll_bg": KEY_COLOR,   # see-through when blur is active
        "accent": "#FFFFFF", "hover": "#DCE3F2", "text": "white", "subtext": "#C9D0E0",
        "button_bg": "#3A4152", "button_hover": "#4D566D",
        "rim": "#B4BED6", "track": "#6C7489",
        "tint": (0x0B, 0x10, 0x1C), "tint_alpha": 0x70,   # colour + strength of the frosted tint (0-255)
        # used instead of the see-through colours if Windows refuses the blur
        "fallback": {"bg_dark": "#1B2030", "panel_bg": "#262D40", "scroll_bg": "#171C2A"},
    }
}
