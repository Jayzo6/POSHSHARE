from dataclasses import dataclass
from typing import List
import re
import time
import random


@dataclass
class ClosetTarget:
	user: str
	max_items: int


def parse_closets_lines(lines: List[str], default_max: int) -> List[ClosetTarget]:
	out: List[ClosetTarget] = []
	for raw in lines:
		line = raw.strip()
		if not line or line.startswith("#"):
			continue
		m = re.match(r"^\s*([A-Za-z0-9_.-]+)\s*(?:[,:\s]\s*(\d+))?\s*$", line)
		if not m:
			continue
		user = m.group(1)
		n = int(m.group(2)) if m.group(2) else int(default_max)
		out.append(ClosetTarget(user=user, max_items=n))
	return out


def format_closets_lines(targets: List[ClosetTarget]) -> str:
	return "\n".join(f"{t.user}, {t.max_items}" for t in targets)


def jitter(a: float = 4.0, b: float = 8.0) -> None:
	time.sleep(random.uniform(a, b))



