from typing import Annotated, Literal, Union
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

ShortText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=300,
    ),
]

class WidgetBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    widget_id: Annotated[
        str,
        StringConstraints(
            pattern=r"^[a-zA-Z0-9_-]{1,64}$",
        ),
    ]
    title: ShortText
    instruction: Annotated[
        str,
        StringConstraints(max_length=1000),
    ] = ""

class QuizOptionSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_id: Annotated[
        str,
        StringConstraints(max_length=16),
    ]
    text: ShortText

class InlineQuizWidgetSchema(WidgetBase):
    type: Literal["inline_quiz"]

    question: Annotated[
        str,
        StringConstraints(
            min_length=1,
            max_length=1000,
        ),
    ]
    options: list[QuizOptionSchema] = Field(
        min_length=2,
        max_length=6,
    )
    correct_option_id: str
    explanation: Annotated[
        str,
        StringConstraints(max_length=1500),
    ] = ""

    @model_validator(mode="after")
    def validate_correct_option(self):
        option_ids = {
            option.option_id
            for option in self.options
        }

        if self.correct_option_id not in option_ids:
            raise ValueError(
                "correct_option_id 必须对应有效选项"
            )

        return self

class SequenceItemSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    text: ShortText

class SequenceSortWidgetSchema(WidgetBase):
    type: Literal["sequence_sort"]

    items: list[SequenceItemSchema] = Field(
        min_length=2,
        max_length=12,
    )
    correct_order: list[str] = Field(
        min_length=2,
        max_length=12,
    )
    success_message: ShortText = "顺序正确。"

    @model_validator(mode="after")
    def validate_sequence(self):
        item_ids = {item.item_id for item in self.items}
        order_ids = set(self.correct_order)
        if item_ids != order_ids or len(self.correct_order) != len(self.items):
            raise ValueError("correct_order 必须与 items 完全对应且无重复")
        return self

class MatchingPairItemSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    text: ShortText

class MatchingPairSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pair_id: str
    left: MatchingPairItemSchema
    right: MatchingPairItemSchema

class MatchingPairsWidgetSchema(WidgetBase):
    type: Literal["matching_pairs"]

    pairs: list[MatchingPairSchema] = Field(
        min_length=2,
        max_length=10,
    )

    @model_validator(mode="after")
    def validate_unique_ids(self):
        pair_ids = set()
        item_ids = set()
        for pair in self.pairs:
            if pair.pair_id in pair_ids:
                raise ValueError(f"pair_id {pair.pair_id} 必须唯一")
            pair_ids.add(pair.pair_id)

            for item in (pair.left, pair.right):
                if item.item_id in item_ids:
                    raise ValueError(f"item_id {item.item_id} 必须全局唯一")
                item_ids.add(item.item_id)
        return self

class TutorialStepSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str
    title: ShortText
    content: Annotated[
        str,
        StringConstraints(max_length=2000),
    ]
    hint: Annotated[
        str,
        StringConstraints(max_length=500),
    ] = ""

class StepperTutorialWidgetSchema(WidgetBase):
    type: Literal["stepper_tutorial"]

    steps: list[TutorialStepSchema] = Field(
        min_length=2,
        max_length=15,
    )

TutorialWidgetSchema = Annotated[
    Union[
        InlineQuizWidgetSchema,
        SequenceSortWidgetSchema,
        MatchingPairsWidgetSchema,
        StepperTutorialWidgetSchema,
    ],
    Field(discriminator="type"),
]

class InteractiveTutorialSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    title: Annotated[
        str,
        StringConstraints(max_length=300),
    ] = ""
    description: Annotated[
        str,
        StringConstraints(max_length=1000),
    ] = ""
    widgets: list[TutorialWidgetSchema] = Field(
        default_factory=list,
        max_length=4,
    )
