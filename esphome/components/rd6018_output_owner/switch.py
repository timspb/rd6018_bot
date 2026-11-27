import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import modbus_controller, switch, text_sensor
from esphome.const import CONF_ID

from . import owner_ns

DEPENDENCIES = ["modbus_controller", "text_sensor"]

OutputOwner = owner_ns.class_("OutputOwner", switch.Switch, cg.Component)

CONFIG_SCHEMA = cv.All(
    switch.switch_schema(OutputOwner)
    .extend(
        {
            cv.Required("modbus_controller_id"): cv.use_id(
                modbus_controller.ModbusController
            ),
            cv.Required("status_sensor_id"): cv.use_id(text_sensor.TextSensor),
        }
    )
    .extend(cv.COMPONENT_SCHEMA)
)

async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await switch.register_switch(var, config)
    parent = await cg.get_variable(config["modbus_controller_id"])
    status = await cg.get_variable(config["status_sensor_id"])
    cg.add(var.set_controller(parent))
    cg.add(var.set_status_sensor(status))
