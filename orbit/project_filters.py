from .models import Project


def filter_projects(
    projects: list[Project], query: str = "", kind: str | None = None,
    state: str | None = None, statuses: dict[int, str] | None = None,
    extra_search: dict[int, str] | None = None,
) -> list[Project]:
    needle = query.strip().casefold()
    statuses = statuses or {}
    extra_search = extra_search or {}
    return [project for project in sorted(projects, key=lambda item: item.name.casefold())
            if (not needle or needle in (
                f"{project.name} {project.description} {project.folder} "
                f"{extra_search.get(project.id, '')}"
            ).casefold())
            and (not kind or project.kind == kind)
            and (not state or statuses.get(project.id, "stopped") == state)]
