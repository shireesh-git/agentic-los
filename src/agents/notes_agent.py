"""Notes-to-accounts agent (roadmap P3): reads the auditor's report, the CARO annexure and the notes of the latest
annual report, in parallel with the analysis agents. Its findings go into the fact pack (``notes_to_accounts``),
so the CAM, the risk strip, the challenges and the Decision Summary quote the same pages."""

from src.agents.base_agent import BaseAgent


class NotesReaderAgent(BaseAgent):
    name = "notes_reader"
    description = "Read the auditor's report, CARO annexure and notes to accounts"
    critical = False            # a report that cannot be read never stops the CAM
    uses_llm = True
    requires = ("data_ingestion",)

    def __init__(self, llm_provider=None):
        self.llm = llm_provider

    def run(self, context):
        from src.engines import notes_reader

        company = context["company_data"]
        fins = company.get("financials") or {}
        net_worth = None
        if fins:
            net_worth = fins[sorted(fins)[-1]].get("total_equity") or None
        entity_id = company["borrower"].entity_id
        notes = notes_reader.for_entity(entity_id, llm=self.llm, net_worth_cr=net_worth)
        self.diagnostics = {"execution_mode": notes.get("mode") or ("empty" if not notes.get("available") else "rules"),
                            "llm_invoked": notes.get("mode") == "ai" and not notes.get("cached"),
                            "llm_calls": 1 if notes.get("mode") == "ai" and not notes.get("cached") else 0}
        return {"notes": notes}
