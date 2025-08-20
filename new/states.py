from aiogram.fsm.state import StatesGroup, State

# class SellerStates(StatesGroup):
#     title = State()
#     description = State()
#     start_price = State()
#     images = State()

class SellerStates(StatesGroup):
    title = State()
    start_price = State()
    description = State()
    model = State()
    images = State()
    memory = State()
    year = State()
    condition = State()
    battery = State()
    repairs = State()
    water = State()
    locks = State()


class BidStates(StatesGroup):
    choosing_lot = State()
    bidding = State()