from PIL import Image

# Open your specific image file
img = Image.open("sonic_logo_4_transparent_1050.png")

# Convert to RGBA to ensure compatibility for the ICO format
if img.mode != "RGBA":
    img = img.convert("RGBA")

# Save as a multi-resolution Windows icon file
img.save(
    "app_icon.ico",
    format="ICO",
    sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
)
print("app_icon.ico generated successfully!")