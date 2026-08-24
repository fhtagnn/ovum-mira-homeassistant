from modbus_connection.model import Component, boolean, int32


class Login(Component):
    status = boolean(100)
    # OVUM requires the 32-bit login code to be written in one FC16 transaction.
    code = int32(101, writable=True, force_fc16=True)


async def login_and_verify(unit, code: int) -> None:
    login = Login(unit)
    await login.write("code", code)
    await login.async_update(notify=False)
    if login.status is not True:
        raise PermissionError("OVUM MIRA Modbus login rejected")
