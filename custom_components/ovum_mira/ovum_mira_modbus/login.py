from modbus_connection.encode import encode_int32


LOGIN_STATUS_REGISTER = 100
LOGIN_CODE_REGISTER = 101


async def login_and_verify(unit, code: int) -> None:
    """Authenticate one OVUM unit and verify only its login status register."""
    # OVUM requires the 32-bit login code to be written in one FC16 transaction.
    # Registers 101/102 are the write payload; only register 100 is read back.
    await unit.write_registers(LOGIN_CODE_REGISTER, encode_int32(code))
    (status,) = await unit.read_holding_registers(LOGIN_STATUS_REGISTER, 1)
    if status != 1:
        raise PermissionError("OVUM MIRA Modbus login rejected")
