"""The agentic LOS API (src/flow): sign-in, the queue, a case and everything done on it."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, Header, UploadFile
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from src.api.dependencies import get_container
from src.application.container import ServiceContainer

router = APIRouter(prefix="/api/flow", tags=["agentic-los"])


def _s(svc: ServiceContainer, token: Optional[str]) -> dict:
    return svc.flow.session(token)


def _pdf(content: bytes, name: str, inline: bool = False) -> Response:
    disp = "inline" if inline else "attachment"
    return Response(content=content, media_type="application/pdf",
                    headers={"Content-Disposition": f'{disp}; filename="{name}"'})


class SignIn(BaseModel):
    user_id: str


class NewCase(BaseModel):
    entity_id: Optional[str] = None
    prospect: Optional[dict] = None
    facility: Optional[dict] = None


class DataPoint(BaseModel):
    value: Any = None
    reason: str = ""
    challenge: str = ""


class Decision(BaseModel):
    decision: str
    comment: str = ""


class Message(BaseModel):
    message: str


class Action(BaseModel):
    action: str
    comment: str = ""
    challenge: str = ""


class Deviation(BaseModel):
    action: str
    mitigant: str = ""
    justification: str = ""
    comment: str = ""


class Response_(BaseModel):
    kind: str = "justify"
    note: str = ""


class Confirm(BaseModel):
    note: str = ""
    reopen: bool = False


class Drawdown(BaseModel):
    amount_cr: Optional[float] = None
    account: Optional[str] = None
    value_date: Optional[str] = None


class Reset(BaseModel):
    entity_id: str


@router.get("/directory")
async def directory(svc: ServiceContainer = Depends(get_container)):
    return svc.flow.directory()


@router.post("/session")
async def sign_in(body: SignIn, svc: ServiceContainer = Depends(get_container)):
    return svc.flow.sign_in(body.user_id)


@router.get("/borrowers")
async def borrowers(x_flow_session: Optional[str] = Header(None), svc: ServiceContainer = Depends(get_container)):
    _s(svc, x_flow_session)
    return svc.flow.borrowers()


@router.get("/queue")
async def queue(x_flow_session: Optional[str] = Header(None), svc: ServiceContainer = Depends(get_container)):
    return svc.flow.queue(_s(svc, x_flow_session))


@router.get("/report")
async def report(x_flow_session: Optional[str] = Header(None), svc: ServiceContainer = Depends(get_container)):
    _s(svc, x_flow_session)
    return svc.flow.time_report()


@router.get("/backtest")
async def backtest(x_flow_session: Optional[str] = Header(None), svc: ServiceContainer = Depends(get_container)):
    _s(svc, x_flow_session)
    return svc.flow.backtest()


@router.post("/backtest/run")
async def run_backtest(x_flow_session: Optional[str] = Header(None), svc: ServiceContainer = Depends(get_container)):
    return svc.flow.run_backtest(_s(svc, x_flow_session))


@router.post("/reset")
async def reset(body: Reset, x_flow_session: Optional[str] = Header(None),
                svc: ServiceContainer = Depends(get_container)):
    return svc.flow.reset(_s(svc, x_flow_session), body.entity_id)


@router.post("/cases")
async def create(body: NewCase, x_flow_session: Optional[str] = Header(None),
                 svc: ServiceContainer = Depends(get_container)):
    s = _s(svc, x_flow_session)
    case = svc.flow.create(s, entity_id=body.entity_id, prospect=body.prospect, facility=body.facility)
    return svc.flow.view(case["case_id"], s)


@router.get("/cases/{case_id}")
async def get_case(case_id: str, x_flow_session: Optional[str] = Header(None),
                   svc: ServiceContainer = Depends(get_container)):
    return svc.flow.view(case_id, _s(svc, x_flow_session))


@router.get("/cases/{case_id}/timeline")
async def timeline(case_id: str, x_flow_session: Optional[str] = Header(None),
                   svc: ServiceContainer = Depends(get_container)):
    _s(svc, x_flow_session)
    return svc.flow.timeline(case_id)


@router.post("/cases/{case_id}/cam/generate")
async def generate(case_id: str, x_flow_session: Optional[str] = Header(None),
                   svc: ServiceContainer = Depends(get_container)):
    return svc.flow.generate_cam(case_id, _s(svc, x_flow_session))


@router.get("/cases/{case_id}/cam/progress")
async def progress(case_id: str, x_flow_session: Optional[str] = Header(None),
                   svc: ServiceContainer = Depends(get_container)):
    _s(svc, x_flow_session)
    return svc.flow.cam_progress(case_id)


@router.post("/cases/{case_id}/cam/upload")
async def upload_cam(case_id: str, file: UploadFile = File(...), x_flow_session: Optional[str] = Header(None),
                     svc: ServiceContainer = Depends(get_container)):
    s = _s(svc, x_flow_session)
    svc.flow.upload_cam(case_id, s, file.filename or "cam.pdf", await file.read())
    return svc.flow.view(case_id, s)


@router.post("/cases/{case_id}/sources/{source_id}/document")
async def upload_source(case_id: str, source_id: str, file: UploadFile = File(...),
                        x_flow_session: Optional[str] = Header(None), svc: ServiceContainer = Depends(get_container)):
    s = _s(svc, x_flow_session)
    svc.flow.upload_source(case_id, s, source_id, file.filename or "document.pdf", await file.read())
    return svc.flow.view(case_id, s)


@router.post("/cases/{case_id}/sources/refresh")
async def refresh_sources(case_id: str, x_flow_session: Optional[str] = Header(None),
                          svc: ServiceContainer = Depends(get_container)):
    s = _s(svc, x_flow_session)
    svc.flow.refresh_sources(case_id, s)
    return svc.flow.view(case_id, s)


@router.get("/cases/{case_id}/sources/{source_id}")
async def source_record(case_id: str, source_id: str, x_flow_session: Optional[str] = Header(None),
                        svc: ServiceContainer = Depends(get_container)):
    _s(svc, x_flow_session)
    return svc.flow.source_record(case_id, source_id)


@router.get("/cases/{case_id}/cam.pdf")
async def cam_pdf(case_id: str, session: Optional[str] = None, x_flow_session: Optional[str] = Header(None),
                  svc: ServiceContainer = Depends(get_container)):
    content, name = svc.flow.cam_file(case_id, _s(svc, x_flow_session or session))
    return _pdf(content, name)


@router.put("/cases/{case_id}/datapoints/{dp_id}")
async def set_datapoint(case_id: str, dp_id: str, body: DataPoint, x_flow_session: Optional[str] = Header(None),
                        svc: ServiceContainer = Depends(get_container)):
    s = _s(svc, x_flow_session)
    svc.flow.set_datapoint(case_id, s, dp_id, body.value, body.reason, challenge=body.challenge)
    return svc.flow.view(case_id, s)


@router.post("/cases/{case_id}/datapoints/{dp_id}/skip")
async def skip_datapoint(case_id: str, dp_id: str, x_flow_session: Optional[str] = Header(None),
                         svc: ServiceContainer = Depends(get_container)):
    s = _s(svc, x_flow_session)
    svc.flow.skip_datapoint(case_id, s, dp_id)
    return svc.flow.view(case_id, s)


@router.post("/cases/{case_id}/checks/{code}")
async def check_note(case_id: str, code: str, body: dict, x_flow_session: Optional[str] = Header(None),
                     svc: ServiceContainer = Depends(get_container)):
    """Record against an open mandatory check: ``{"kind": "verified" | "justified", "note"}``."""
    return svc.flow.check_note(case_id, code, body, _s(svc, x_flow_session))


@router.post("/cases/{case_id}/changes/{change_id}")
async def decide_change(case_id: str, change_id: str, body: Decision, x_flow_session: Optional[str] = Header(None),
                        svc: ServiceContainer = Depends(get_container)):
    s = _s(svc, x_flow_session)
    svc.flow.decide_change(case_id, s, change_id, body.decision, body.comment)
    return svc.flow.view(case_id, s)


@router.post("/cases/{case_id}/chat")
async def chat(case_id: str, body: Message, x_flow_session: Optional[str] = Header(None),
               svc: ServiceContainer = Depends(get_container)):
    s = _s(svc, x_flow_session)
    svc.flow.chat(case_id, s, body.message)
    return svc.flow.view(case_id, s)


class Remark(BaseModel):
    text: str = ""


class Query(BaseModel):
    question: str = ""
    to_stage: Optional[str] = None


class Archive(BaseModel):
    archived: bool = True


@router.post("/cases/{case_id}/verification/{check_id}/explain")
async def explain_verification(case_id: str, check_id: str, body: Remark, x_flow_session: Optional[str] = Header(None),
                               svc: ServiceContainer = Depends(get_container)):
    s = _s(svc, x_flow_session)
    svc.flow.explain_verification(case_id, s, check_id, body.text)
    return svc.flow.view(case_id, s)


@router.post("/cases/{case_id}/withdraw")
async def withdraw(case_id: str, body: Remark, x_flow_session: Optional[str] = Header(None),
                   svc: ServiceContainer = Depends(get_container)):
    s = _s(svc, x_flow_session)
    svc.flow.withdraw(case_id, s, body.text)
    return svc.flow.view(case_id, s)


@router.post("/cases/{case_id}/archive")
async def archive(case_id: str, body: Archive, x_flow_session: Optional[str] = Header(None),
                  svc: ServiceContainer = Depends(get_container)):
    s = _s(svc, x_flow_session)
    svc.flow.archive(case_id, s, body.archived)
    return svc.flow.view(case_id, s)


@router.delete("/cases/{case_id}")
async def delete_case(case_id: str, x_flow_session: Optional[str] = Header(None),
                      svc: ServiceContainer = Depends(get_container)):
    return svc.flow.delete_case(case_id, _s(svc, x_flow_session))


@router.post("/cases/{case_id}/queries")
async def raise_query(case_id: str, body: Query, x_flow_session: Optional[str] = Header(None),
                      svc: ServiceContainer = Depends(get_container)):
    s = _s(svc, x_flow_session)
    svc.flow.raise_query(case_id, s, body.question, body.to_stage)
    return svc.flow.view(case_id, s)


@router.post("/cases/{case_id}/queries/{qid}/answer")
async def answer_query(case_id: str, qid: str, body: Remark, x_flow_session: Optional[str] = Header(None),
                       svc: ServiceContainer = Depends(get_container)):
    s = _s(svc, x_flow_session)
    svc.flow.answer_query(case_id, s, qid, body.text)
    return svc.flow.view(case_id, s)


@router.post("/cases/{case_id}/queries/{qid}/withdraw")
async def withdraw_query(case_id: str, qid: str, x_flow_session: Optional[str] = Header(None),
                         svc: ServiceContainer = Depends(get_container)):
    s = _s(svc, x_flow_session)
    svc.flow.withdraw_query(case_id, s, qid)
    return svc.flow.view(case_id, s)


@router.post("/cases/{case_id}/action")
async def act(case_id: str, body: Action, x_flow_session: Optional[str] = Header(None),
              svc: ServiceContainer = Depends(get_container)):
    s = _s(svc, x_flow_session)
    svc.flow.act(case_id, s, body.action, body.comment, body.challenge)
    return svc.flow.view(case_id, s)


@router.post("/cases/{case_id}/deviations/{deviation_id}")
async def deviation(case_id: str, deviation_id: str, body: Deviation, x_flow_session: Optional[str] = Header(None),
                    svc: ServiceContainer = Depends(get_container)):
    s = _s(svc, x_flow_session)
    svc.flow.deviation(case_id, s, deviation_id, body.action, body.mitigant, body.justification, body.comment)
    return svc.flow.view(case_id, s)


@router.post("/cases/{case_id}/challenges/{challenge_id}")
async def respond(case_id: str, challenge_id: str, body: Response_, x_flow_session: Optional[str] = Header(None),
                  svc: ServiceContainer = Depends(get_container)):
    s = _s(svc, x_flow_session)
    svc.flow.respond(case_id, s, challenge_id, body.kind, body.note)
    return svc.flow.view(case_id, s)


@router.post("/cases/{case_id}/conditions/{condition_id}/document")
async def upload_document(case_id: str, condition_id: str, file: UploadFile = File(...),
                          x_flow_session: Optional[str] = Header(None), svc: ServiceContainer = Depends(get_container)):
    s = _s(svc, x_flow_session)
    svc.flow.upload_document(case_id, s, condition_id, file.filename or "document.pdf", await file.read())
    return svc.flow.view(case_id, s)


@router.get("/cases/{case_id}/conditions/{condition_id}/document/{index}")
async def get_document(case_id: str, condition_id: str, index: int, session: Optional[str] = None,
                       x_flow_session: Optional[str] = Header(None), svc: ServiceContainer = Depends(get_container)):
    _s(svc, x_flow_session or session)
    content, name = svc.flow.document_file(case_id, condition_id, index)
    return _pdf(content, name, inline=True)


@router.post("/cases/{case_id}/conditions/{condition_id}/confirm")
async def confirm(case_id: str, condition_id: str, body: Confirm, x_flow_session: Optional[str] = Header(None),
                  svc: ServiceContainer = Depends(get_container)):
    s = _s(svc, x_flow_session)
    svc.flow.confirm_condition(case_id, s, condition_id, body.note, body.reopen)
    return svc.flow.view(case_id, s)


@router.post("/cases/{case_id}/demo-documents")
async def demo_documents(case_id: str, x_flow_session: Optional[str] = Header(None),
                         svc: ServiceContainer = Depends(get_container)):
    s = _s(svc, x_flow_session)
    svc.flow.demo_documents(case_id, s)
    return svc.flow.view(case_id, s)


@router.put("/cases/{case_id}/drawdown")
async def drawdown(case_id: str, body: Drawdown, x_flow_session: Optional[str] = Header(None),
                   svc: ServiceContainer = Depends(get_container)):
    s = _s(svc, x_flow_session)
    svc.flow.set_drawdown(case_id, s, body.amount_cr, body.account, body.value_date)
    return svc.flow.view(case_id, s)


@router.get("/cases/{case_id}/sanction-letter.html", response_class=HTMLResponse)
async def sanction_letter(case_id: str, session: Optional[str] = None, x_flow_session: Optional[str] = Header(None),
                          svc: ServiceContainer = Depends(get_container)):
    _s(svc, x_flow_session or session)
    return HTMLResponse(svc.flow.sanction_letter(case_id))


@router.get("/cases/{case_id}/audit-pack.html", response_class=HTMLResponse)
async def audit_pack(case_id: str, session: Optional[str] = None, x_flow_session: Optional[str] = Header(None),
                     svc: ServiceContainer = Depends(get_container)):
    return HTMLResponse(svc.flow.audit_pack(case_id, _s(svc, x_flow_session or session)))


@router.get("/cases/{case_id}/ai-governance.html", response_class=HTMLResponse)
async def ai_governance(case_id: str, session: Optional[str] = None, x_flow_session: Optional[str] = Header(None),
                        svc: ServiceContainer = Depends(get_container)):
    return HTMLResponse(svc.flow.governance_html(case_id, _s(svc, x_flow_session or session)))


@router.get("/cases/{case_id}/ai-governance.json")
async def ai_governance_json(case_id: str, session: Optional[str] = None, x_flow_session: Optional[str] = Header(None),
                             svc: ServiceContainer = Depends(get_container)):
    return svc.flow.governance(case_id, _s(svc, x_flow_session or session))


@router.get("/cases/{case_id}/audit-pack.json")
async def audit_json(case_id: str, session: Optional[str] = None, x_flow_session: Optional[str] = Header(None),
                     svc: ServiceContainer = Depends(get_container)):
    _s(svc, x_flow_session or session)
    return svc.flow.audit_json(case_id)
