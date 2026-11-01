from pydantic import BaseModel, Field

class RecruitRequest(BaseModel):
    count: int = Field(ge=1, le=100)


class DeclareWarRequest(BaseModel):
    attack_city_key: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")
    target_city_key: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")

class CreateAllianceRequest(BaseModel):
    name: str = Field(min_length=3, max_length=64)
    tag: str = Field(min_length=2, max_length=5, pattern=r"^[A-Za-z0-9]+$")

class JoinAllianceRequest(BaseModel):
    alliance_id: int = Field(gt=0)

class ManageAllianceRequest(BaseModel):
    accept: bool

class TransferLeadershipRequest(BaseModel):
    new_leader_id: int = Field(gt=0)

class KickAllianceMemberRequest(BaseModel):
    telegram_id: int = Field(gt=0)

class AllianceMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)

class AlliancePactRequest(BaseModel):
    alliance_id: int = Field(gt=0)

class DecideAlliancePactRequest(BaseModel):
    accept: bool


class DeclareAllianceWarRequest(BaseModel):
    target_city_key: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")


class SupportAllianceWarRequest(BaseModel):
    coins: int = Field(ge=10, le=1000)


class AllianceTreasuryTransferRequest(BaseModel):
    amount: int = Field(ge=10, le=10_000)

class AllianceBuildingUpgradeRequest(BaseModel):
    building: str = Field(pattern=r"^(fortress|academy)$")


class AllianceRankRequest(BaseModel):
    telegram_id: int = Field(gt=0)
    rank: str = Field(pattern=r"^(commander|treasurer|officer|member)$")


class AllianceNotificationPreferencesRequest(BaseModel):
    telegram_enabled: bool = True
    categories: dict[str, bool] = Field(default_factory=dict)

class MarkAllianceNotificationReadRequest(BaseModel):
    notification_id: int | None = Field(default=None, gt=0)


class AllianceProposalRequest(BaseModel):
    title: str = Field(min_length=5, max_length=100)
    description: str = Field(min_length=10, max_length=1000)
    duration_hours: int = Field(default=24, ge=1, le=72)

class AllianceVoteRequest(BaseModel):
    choice: str = Field(pattern=r"^(yes|no)$")


class EquipmentPurchaseRequest(BaseModel):
    item_key: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")
    quantity: int = Field(default=1, ge=1, le=10)

class EquipmentEquipRequest(BaseModel):
    item_key: str | None = Field(default=None, min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")
    item_id: str | None = Field(default=None, min_length=1, max_length=40)
    # فرانت قدیمی item_id می‌فرستاد

    def resolved_key(self) -> str:
        key = (self.item_key or self.item_id or "").strip()
        if not key:
            raise ValueError("item_key لازم است")
        return key

class EquipmentBoxRequest(BaseModel):
    request_id: str | None = Field(default=None, min_length=8, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")


class StaffGrantRequest(BaseModel):
    telegram_id: int = Field(gt=0)
    role: str = Field(min_length=3, max_length=20)
    note: str = Field(default="", max_length=200)


class StaffRevokeRequest(BaseModel):
    telegram_id: int = Field(gt=0)


class StaffBanRequest(BaseModel):
    telegram_id: int = Field(gt=0)
    banned: bool = True


class StaffCoinsRequest(BaseModel):
    telegram_id: int = Field(gt=0)
    amount: int
    mode: str = Field(default="add", pattern=r"^(add|set)$")


class StaffDeleteChatRequest(BaseModel):
    message_id: int = Field(gt=0)
