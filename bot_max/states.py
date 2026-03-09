"""FSM-состояния MAX-бота (maxapi StatesGroup)."""

from maxapi.context import StatesGroup, State


class MaxStates(StatesGroup):
    menu = State()
    upload_photo = State()
    request_occasion = State()
    request_season = State()
    generating = State()
    setting_city = State()
