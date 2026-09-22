from modbus_connection.encode import encode_int32


LOGIN_STATUS_REGISTER = 100
LOGIN_CODE_REGISTER = 101


async def is_login_granted(unit) -> bool:
    """Return whether one OVUM unit currently grants authenticated access."""
    status = await unit.read_holding_registers(LOGIN_STATUS_REGISTER, 1)
    return len(status) == 1 and status[0] == 1


async def login_and_verify(unit, code: int) -> None:
    """Authenticate one OVUM unit and verify only its login status register."""
    # OVUM requires the 32-bit login code to be written in one FC16 transaction.
    # Registers 101/102 are the write payload; only register 100 is read back.
    await unit.write_registers(LOGIN_CODE_REGISTER, encode_int32(code))
    if not await is_login_granted(unit):
        raise PermissionError("OVUM MIRA Modbus login rejected")
