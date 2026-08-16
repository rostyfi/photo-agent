from unittest.mock import patch


def find_callback(app, output_id, output_prop):
    """Find a callback wrapper from app.callback_map by its output id/prop.

    Handles both plain keys and hashed allow_duplicate keys.
    Returns the Dash wrapper; use .__wrapped__ to call the raw function.
    """
    for _k, v in app.callback_map.items():
        out = v.get("output")
        outs = out if isinstance(out, list) else [out]
        for o in outs:
            cid = getattr(o, "component_id", o)
            cprop = getattr(o, "component_property", o)
            if cid == output_id and cprop == output_prop:
                return v["callback"]
    raise KeyError(f"No callback found for {output_id}.{output_prop}")


def make_mock_ctx(triggered):
    """Return a mock callback_context object for unit tests."""
    return type(
        "_MockCtx",
        (),
        {
            "triggered": triggered,
            "triggered_id": (triggered[0]["prop_id"].rsplit(".", 1)[0] if triggered else None),
            "triggered_prop_ids": {t["prop_id"]: t.get("value") for t in triggered},
        },
    )()


def patch_callback_context(module, triggered):
    """Return a unittest.mock.patch.object for the module's callback_context."""
    return patch.object(module, "callback_context", make_mock_ctx(triggered))
