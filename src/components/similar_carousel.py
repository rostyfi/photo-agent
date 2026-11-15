"""Builder for the similar-photos carousel shown in the detail modal."""

import dash_bootstrap_components as dbc
from dash import html

from .preview import _preview_url


def build_similar_photos_carousel(similar_data, folder):
    """Build a carousel of similar photos with similarity scores.

    Args:
        similar_data: Dict with 'images' and 'scores' keys, or None.
        folder: Current folder path for preview URLs.

    Returns:
        A ``dash.html.Div`` containing the similar photos carousel, or empty if no data.
    """
    if not similar_data or not similar_data.get("images"):
        return html.Div()

    images = similar_data.get("images", [])
    scores = similar_data.get("scores", [])

    items = []
    for _i, (image_path, score) in enumerate(zip(images, scores, strict=False)):
        preview_url = _preview_url(image_path, folder, size="thumb")
        score_pct = score * 100
        filename = image_path.split("/")[-1] if "/" in image_path else image_path

        items.append(
            dbc.Col(
                html.Div(
                    [
                        html.Img(
                            src=preview_url,
                            style={
                                "maxWidth": "120px",
                                "maxHeight": "120px",
                                "objectFit": "cover",
                                "cursor": "pointer",
                            },
                            className="img-thumbnail mb-1",
                            id={"type": "similar-thumbnail", "index": image_path},
                            n_clicks=0,
                        ),
                        html.Small(
                            [
                                html.Strong(f"{score_pct:.1f}% "),
                                html.Span(filename, className="text-muted"),
                            ],
                            className="d-block text-center",
                        ),
                    ],
                    className="text-center mb-2",
                    style={"cursor": "pointer"},
                ),
                width="auto",
            )
        )

    return html.Div(
        [
            html.H6("Similar Photos", className="mt-3 mb-2"),
            dbc.Row(items, className="g-2 flex-wrap"),
        ]
    )
