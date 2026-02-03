#!/usr/bin/env python3
"""
Generate the menu bar icon for Atmosphere.

Creates a simple mesh/cloud icon as a template image for macOS menu bar.
Template images should be black with alpha transparency.
"""

from pathlib import Path

def generate_icon_pillow():
    """Generate icon using Pillow."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("Pillow not installed. Run: pip install pillow")
        return None
    
    # Menu bar icons should be 18x18 or 22x22 at 1x
    # For retina, we create 44x44 and let macOS scale
    size = 44
    
    # Create transparent image
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw a simple mesh/network icon
    # Three connected nodes forming a triangle
    center = size // 2
    radius = size // 3
    node_radius = size // 10
    
    import math
    
    # Calculate node positions (triangle)
    nodes = []
    for i in range(3):
        angle = (i * 120 - 90) * math.pi / 180  # Start from top
        x = center + int(radius * math.cos(angle))
        y = center + int(radius * math.sin(angle))
        nodes.append((x, y))
    
    # Draw connections (lines between nodes) - black for template
    line_color = (0, 0, 0, 180)
    for i, n1 in enumerate(nodes):
        for n2 in nodes[i+1:]:
            draw.line([n1, n2], fill=line_color, width=2)
    
    # Draw nodes as circles
    node_color = (0, 0, 0, 255)
    for x, y in nodes:
        draw.ellipse(
            [x - node_radius, y - node_radius, x + node_radius, y + node_radius],
            fill=node_color
        )
    
    # Add a small center dot
    center_radius = node_radius // 2
    draw.ellipse(
        [center - center_radius, center - center_radius, 
         center + center_radius, center + center_radius],
        fill=node_color
    )
    
    return img


def generate_simple_icon():
    """Generate a simple A icon if Pillow isn't available."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("Pillow not installed. Creating placeholder...")
        return None
    
    size = 44
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw a simple "A" or circle
    padding = 6
    draw.ellipse(
        [padding, padding, size - padding, size - padding],
        outline=(0, 0, 0, 255),
        width=3
    )
    
    # Draw mesh lines inside
    center = size // 2
    r = (size - padding * 2) // 3
    
    # Simple three-line mesh pattern
    draw.line([(center, padding + 4), (center, size - padding - 4)], fill=(0, 0, 0, 200), width=2)
    draw.line([(padding + 4, center), (size - padding - 4, center)], fill=(0, 0, 0, 200), width=2)
    
    return img


def main():
    output_dir = Path(__file__).parent
    output_path = output_dir / "icon.png"
    
    # Try to generate the mesh icon
    img = generate_icon_pillow()
    
    if img is None:
        img = generate_simple_icon()
    
    if img is None:
        print("Could not generate icon. Please install Pillow: pip install pillow")
        print("Or manually create a 44x44 PNG at:", output_path)
        return
    
    # Save the icon
    img.save(output_path, "PNG")
    print(f"✓ Icon saved to: {output_path}")
    
    # Also create a 2x version for retina
    retina_path = output_dir / "icon@2x.png"
    img.save(retina_path, "PNG")
    print(f"✓ Retina icon saved to: {retina_path}")


if __name__ == "__main__":
    main()
