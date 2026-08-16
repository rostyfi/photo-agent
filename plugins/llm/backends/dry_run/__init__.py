from plugins.llm.registry import register_backend


def _dry_run_factory(**kwargs):
    from plugins.llm.dry_run import DryRunPhotoExtractor

    return DryRunPhotoExtractor(**kwargs)


register_backend("dry_run", _dry_run_factory)
