"""The field registry (config/los_fields.yaml): domains, verify policies, resolvers."""

from __future__ import annotations

from dataclasses import dataclass

VERIFY_POLICIES = ("bulk", "must_verify")


@dataclass(frozen=True)
class FieldSpec:
    field_id: str
    domain: str
    verify: str = "bulk"


class FieldRegistry:
    def __init__(self, cfg: dict | None):
        cfg = cfg or {}
        self.version = cfg.get("version", 1)
        verify = cfg.get("verify") or {}
        self.pretick_confidence = float(verify.get("pretick_confidence", 0.85))
        self.history_limit = int(verify.get("history_limit", 20))
        self.provenance_confidence = {k: float(v) for k, v in (cfg.get("provenance_confidence") or {}).items()}
        self.domains: dict[str, dict] = {k: dict(v or {}) for k, v in (cfg.get("domains") or {}).items()}
        self.resolvers: dict[str, dict] = {k: dict(v or {}) for k, v in (cfg.get("resolvers") or {}).items()}
        self._fields: dict[str, dict] = {k: dict(v or {}) for k, v in (cfg.get("fields") or {}).items()}
        for fid, f in self._fields.items():
            if f.get("verify", "bulk") not in VERIFY_POLICIES:
                raise ValueError(f"los_fields.yaml: {fid}: verify must be one of {VERIFY_POLICIES}")

    @classmethod
    def load(cls) -> "FieldRegistry":
        from src.core.config_manager import config
        return cls(config.get("los_fields", default={}) or {})

    @staticmethod
    def domain_of(field_id: str) -> str:
        return field_id.split(".", 1)[0]

    def spec(self, field_id: str) -> FieldSpec:
        f = self._fields.get(field_id) or {}
        return FieldSpec(field_id=field_id, domain=f.get("domain") or self.domain_of(field_id),
                         verify=f.get("verify", "bulk"))

    def domain_label(self, domain: str) -> str:
        return (self.domains.get(domain) or {}).get("label") or domain.replace("_", " ").title()

    def domains_verified_at(self, step_id: str | None) -> list[str]:
        return [d for d, cfg in self.domains.items() if step_id and step_id in (cfg.get("verify_at") or [])]

    def verifiable_at(self, field_id: str, step_id: str | None) -> bool:
        return self.spec(field_id).domain in self.domains_verified_at(step_id)

    def confidence_for(self, provenance: str | None) -> float:
        return self.provenance_confidence.get(provenance or "", 0.5)
