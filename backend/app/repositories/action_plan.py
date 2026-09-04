"""Action plan persistence operations."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ActionPlan
from app.schemas.action_plan import ActionPlanCreate


class ActionPlanRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, data: ActionPlanCreate) -> ActionPlan:
        plan = self.get_for_mission(data.mission_id)
        values = {
            "title": data.title,
            "summary": data.summary,
            "tasks_json": [task.model_dump(mode="json") for task in data.tasks_json],
            "success_metrics_json": data.success_metrics_json,
            "estimated_effort": data.estimated_effort,
        }
        if plan is None:
            plan = ActionPlan(mission_id=str(data.mission_id), **values)
            self.session.add(plan)
        else:
            for field, value in values.items():
                setattr(plan, field, value)
        self.session.commit()
        self.session.refresh(plan)
        return plan

    def get_for_mission(self, mission_id: UUID | str) -> ActionPlan | None:
        statement = select(ActionPlan).where(ActionPlan.mission_id == str(mission_id))
        return self.session.scalar(statement)
