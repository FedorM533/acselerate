"""QR-код для сопряжения: готовая SVG-картинка, чтобы интерфейсу не нужны были библиотеки."""


def qr_svg(text: str) -> str:
    import segno      # лёгкая библиотека на чистом Python
    return segno.make(text, error="m").svg_inline(scale=6, border=2, dark="#000000", light="#ffffff")
