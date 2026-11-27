#pragma once
#include <array>
#include <string>

#include "esphome/components/modbus/modbus.h"
#include "esphome/components/modbus_controller/modbus_controller.h"
#include "esphome/components/switch/switch.h"
#include "esphome/components/text_sensor/text_sensor.h"
#include "esphome/core/component.h"

namespace esphome::rd6018_output_owner {
class OutputOwner : public switch_::Switch, public Component, public modbus::ModbusClientDevice {
 public:
  void set_controller(modbus_controller::ModbusController *controller) { controller_ = controller; }
  void set_status_sensor(text_sensor::TextSensor *sensor) { status_sensor_ = sensor; }
  void setup() override;
  float get_setup_priority() const override { return -20.0f; }
  void request(const std::string &request_id, bool enabled);
  void observe_readback(uint16_t value);
  void write_state(bool state) override { this->request("switch", state); }
  void on_sent(std::span<const uint8_t> request_pdu) override;
  void on_not_sent(std::span<const uint8_t> request_pdu) override;
  bool on_no_response(std::span<const uint8_t> request_pdu) override;
  void on_error(std::span<const uint8_t> request_pdu, modbus::ExceptionCode code) override;
  void on_read_holding_registers(uint16_t address, std::span<const uint16_t> values,
                                modbus::ResponseStatus status) override;
  void on_write_single_register(uint16_t address, uint16_t value, modbus::ResponseStatus status) override;

 protected:
  enum class Frame { NONE, WRITE, READBACK };
  struct ReceiptRecord {
    bool valid{false};
    std::string request_id;
    bool target{false};
    std::string state;
    uint16_t observed{0};
    bool observed_valid{false};
    uint8_t exception{0};
    uint32_t write_sent_ms{0};
    uint32_t read_sent_ms{0};
    uint32_t write_send_generation{0};
    uint32_t read_send_generation{0};
  };
  const ReceiptRecord *find_receipt_(const std::string &request_id) const;
  void remember_receipt_(const char *state);
  void publish_cached_(const ReceiptRecord &receipt);
  void publish_terminal_(const char *state, const char *extra = nullptr);
  void publish_(const char *state, const char *extra = nullptr);
  void uncertain_(const char *reason);
  modbus_controller::ModbusController *controller_{nullptr};
  text_sensor::TextSensor *status_sensor_{nullptr};
  std::string request_id_;
  bool target_{false};
  bool active_{false};
  bool sent_{false};
  uint32_t write_sent_ms_{0};
  uint32_t read_sent_ms_{0};
  uint32_t send_generation_{0};
  uint32_t write_send_generation_{0};
  uint32_t read_send_generation_{0};
  Frame frame_{Frame::NONE};
  uint16_t observed_{0};
  bool observed_valid_{false};
  uint8_t exception_{0};
  std::array<ReceiptRecord, 8> receipts_{};
  uint8_t receipt_cursor_{0};
};
}  // namespace esphome::rd6018_output_owner
