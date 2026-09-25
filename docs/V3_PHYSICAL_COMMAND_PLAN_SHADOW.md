# V3 physical command plan and bench shadow

`build_command_plan()` превращает `SafeOutputIntent` в неизменяемый список
ожидаемых шагов. План содержит `execution_allowed=False` и не имеет метода
исполнения. `BenchExecutionShadow` принимает только внешнее observation и
сравнивает его с планом; это не драйвер и не physical test controller.

Последовательности:

- ENABLE: prepare → set V/I → set OVP/OCP → readback/compare → enable.
- DISABLE: disable → read output state → confirm OFF → reset protection.
- RESET: reset OVP/OCP → readback/compare.

Этот этап не выполняет ни одной команды и не подключается к RD, HA, lease или
production runtime. V1 UI остаётся отдельным потоком.
