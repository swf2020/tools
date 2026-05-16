from dataclasses import dataclass, field


@dataclass
class Blog:
    file_path: str = ""
    title: str = ""
    content: str = ""
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    cover_img_path: str = ""
    categories: list[str] = field(default_factory=list)
