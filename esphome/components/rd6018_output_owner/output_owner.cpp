#include "output_owner.h"
#include "esphome/core/log.h"

#include <cstdio>
#include <string>

namespace esphome::rd6018_output_owner {
static const char *const TAG = "rd6018_output_owner";

void OutputOwner::setup() {
  if (this->controller_ == nullptr || this->controller_->hub() == nullptr) {
    ESP_LOGE(TAG, "powersupply Modbus hub unavailable");
    this->mark_failed();
    return;
  }
  this->set_parent(this->controller_->hub());
  this->set_address(this->controller_->device_address());
}

void OutputOwner::publish_(const char *state, const char *extra) {
  if (this->status_sensor_ == nullptr) return;
  char escaped_id[97];
  size_t escaped_len = 0;
  for (size_t i = 0; i < this->request_id_.size() && i < 48 && escaped_len < sizeof(escaped_id) - 2; i++) {
    const char ch = this->request_id_[i];
    if (ch == '\\' || ch == '"') escaped_id[escaped_len++] = '\\';
    escaped_id[escaped_len++] = (static_cast<uint8_t>(ch) < 0x20) ? '_' : ch;
  }
  escaped_id[escaped_len] = '\0';
  char out[384];
  const char *observed = !this->observed_valid_ ? "null" : (this->observed_ & 1 ? "1" : "0");
  if (extra != nullptr)
    snprintf(out, sizeof(out), "{\"request_id\":\"%s\",\"target\":%s,\"state\":\"%s\",\"observed_r18\":%s,\"exception\":%u,\"write_sent_ms\":%lu,\"write_send_generation\":%lu,\"read_sent_ms\":%lu,\"read_send_generation\":%lu}",
             escaped_id, this->target_ ? "true" : "false", state, observed, this->exception_,
             static_cast<unsigned long>(this->write_sent_ms_), static_cast<unsigned long>(this->write_send_generation_),
             static_cast<unsigned long>(this->read_sent_ms_), static_cast<unsigned long>(this->read_send_generation_));
  else
    snprintf(out, sizeof(out), "{\"request_id\":\"%s\",\"target\":%s,\"state\":\"%s\",\"observed_r18\":%s,\"write_sent_ms\":%lu,\"write_send_generation\":%lu,\"read_sent_ms\":%lu,\"read_send_generation\":%lu}",
             escaped_id, this->target_ ? "true" : "false", state, observed,
             static_cast<unsigned long>(this->write_sent_ms_), static_cast<unsigned long>(this->write_send_generation_),
             static_cast<unsigned long>(this->read_sent_ms_), static_cast<unsigned long>(this->read_send_generation_));
  this->status_sensor_->publish_state(out);
}

const OutputOwner::ReceiptRecord *OutputOwner::find_receipt_(const std::string &request_id) const {
  for (const auto &receipt : this->receipts_) {
    if (receipt.valid && receipt.request_id == request_id) return &receipt;
  }
  return nullptr;
}

void OutputOwner::remember_receipt_(const char *state) {
  if (this->request_id_.empty() || this->request_id_ == "switch" || this->request_id_ == "invalid") return;
  ReceiptRecord *slot = nullptr;
  for (auto &receipt : this->receipts_) {
    if (receipt.valid && receipt.request_id == this->request_id_) {
      slot = &receipt;
      break;
    }
  }
  if (slot == nullptr) {
    slot = &this->receipts_[this->receipt_cursor_ % this->receipts_.size()];
    this->receipt_cursor_ = static_cast<uint8_t>((this->receipt_cursor_ + 1) % this->receipts_.size());
  }
  slot->valid = true;
  slot->request_id = this->request_id_;
  slot->target = this->target_;
  slot->state = state;
  slot->observed = this->observed_;
  slot->observed_valid = this->observed_valid_;
  slot->exception = this->exception_;
  slot->write_sent_ms = this->write_sent_ms_;
  slot->read_sent_ms = this->read_sent_ms_;
  slot->write_send_generation = this->write_send_generation_;
  slot->read_send_generation = this->read_send_generation_;
}

void OutputOwner::publish_terminal_(const char *state, const char *extra) {
  this->remember_receipt_(state);
  this->publish_(state, extra);
}

void OutputOwner::publish_cached_(const ReceiptRecord &receipt) {
  const std::string saved_id = this->request_id_;
  const bool saved_target = this->target_;
  const uint16_t saved_observed = this->observed_;
  const bool saved_observed_valid = this->observed_valid_;
  const uint8_t saved_exception = this->exception_;
  const uint32_t saved_write_sent_ms = this->write_sent_ms_;
  const uint32_t saved_read_sent_ms = this->read_sent_ms_;
  const uint32_t saved_write_generation = this->write_send_generation_;
  const uint32_t saved_read_generation = this->read_send_generation_;
  this->request_id_ = receipt.request_id;
  this->target_ = receipt.target;
  this->observed_ = receipt.observed;
  this->observed_valid_ = receipt.observed_valid;
  this->exception_ = receipt.exception;
  this->write_sent_ms_ = receipt.write_sent_ms;
  this->read_sent_ms_ = receipt.read_sent_ms;
  this->write_send_generation_ = receipt.write_send_generation;
  this->read_send_generation_ = receipt.read_send_generation;
  this->publish_(receipt.state.c_str(), receipt.exception != 0 ? "exception" : nullptr);
  this->request_id_ = saved_id;
  this->target_ = saved_target;
  this->observed_ = saved_observed;
  this->observed_valid_ = saved_observed_valid;
  this->exception_ = saved_exception;
  this->write_sent_ms_ = saved_write_sent_ms;
  this->read_sent_ms_ = saved_read_sent_ms;
  this->write_send_generation_ = saved_write_generation;
  this->read_send_generation_ = saved_read_generation;
  if (this->active_ && this->request_id_ != receipt.request_id) {
    this->publish_(this->frame_ == Frame::READBACK ? "ACKNOWLEDGED_WAITING_READBACK" : "ACCEPTED");
  }
}

void OutputOwner::uncertain_(const char *reason) {
  if (reason != nullptr) ESP_LOGW(TAG, "R18 command uncertain: %s", reason);
  this->active_ = false;
  this->frame_ = Frame::NONE;
  this->publish_terminal_("OUTCOME_UNCERTAIN", this->exception_ != 0 ? "exception" : nullptr);
}

void OutputOwner::request(const std::string &request_id, bool enabled) {
  bool valid_id = !request_id.empty() && request_id.size() <= 48;
  for (const unsigned char ch : request_id) {
    if (!((ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z') ||
          (ch >= '0' && ch <= '9') || ch == '-' || ch == '_')) {
      valid_id = false;
      break;
    }
  }
  if (!valid_id) {
    const std::string previous_id = this->request_id_;
    const bool previous_active = this->active_;
    const bool previous_target = this->target_;
    const Frame previous_frame = this->frame_;
    this->request_id_ = "invalid";
    this->target_ = enabled;
    this->publish_("NOT_QUEUED");
    if (previous_active) {
      this->request_id_ = previous_id;
      this->target_ = previous_target;
      this->publish_(previous_frame == Frame::READBACK ? "ACKNOWLEDGED_WAITING_READBACK" : "ACCEPTED");
    }
    return;
  }

  if (request_id != "switch") {
    const ReceiptRecord *cached = this->find_receipt_(request_id);
    if (cached != nullptr) {
      if (cached->target == enabled) {
        this->publish_cached_(*cached);
      } else {
        const std::string saved_id = this->request_id_;
        const bool saved_target = this->target_;
        const uint16_t saved_observed = this->observed_;
        const bool saved_observed_valid = this->observed_valid_;
        const uint8_t saved_exception = this->exception_;
        const uint32_t saved_write_sent_ms = this->write_sent_ms_;
        const uint32_t saved_read_sent_ms = this->read_sent_ms_;
        const uint32_t saved_write_generation = this->write_send_generation_;
        const uint32_t saved_read_generation = this->read_send_generation_;
        this->request_id_ = request_id;
        this->target_ = enabled;
        this->observed_ = cached->observed;
        this->observed_valid_ = cached->observed_valid;
        this->exception_ = 0;
        this->write_sent_ms_ = cached->write_sent_ms;
        this->read_sent_ms_ = cached->read_sent_ms;
        this->write_send_generation_ = cached->write_send_generation;
        this->read_send_generation_ = cached->read_send_generation;
        this->publish_("REJECTED");
        this->request_id_ = saved_id;
        this->target_ = saved_target;
        this->observed_ = saved_observed;
        this->observed_valid_ = saved_observed_valid;
        this->exception_ = saved_exception;
        this->write_sent_ms_ = saved_write_sent_ms;
        this->read_sent_ms_ = saved_read_sent_ms;
        this->write_send_generation_ = saved_write_generation;
        this->read_send_generation_ = saved_read_generation;
        if (this->active_) {
          this->publish_(this->frame_ == Frame::READBACK ? "ACKNOWLEDGED_WAITING_READBACK" : "ACCEPTED");
        }
      }
      return;
    }
  }

  if (this->active_ && this->target_ == enabled) {
    const char *pending_state = this->frame_ == Frame::READBACK ? "ACKNOWLEDGED_WAITING_READBACK" : "ACCEPTED";
    if (request_id == this->request_id_) {
      this->publish_(pending_state);
      return;
    }
    // A local switch request has no waiter. Let a correlated Native request adopt
    // that same in-flight operation, but never let a later local OFF steal its ID.
    if (this->request_id_ == "switch" && request_id != "switch") {
      this->request_id_ = request_id;
      this->publish_(pending_state);
      return;
    }
    if (request_id == "switch") return;

    // A second distinct Native request is not allowed to replace the first receipt
    // or enqueue another frame. Publish NOT_QUEUED for the newcomer, then restore
    // the active request's latest state for its original waiter.
    const std::string active_id = this->request_id_;
    const bool active_target = this->target_;
    const uint16_t active_observed = this->observed_;
    const bool active_observed_valid = this->observed_valid_;
    const uint8_t active_exception = this->exception_;
    const uint32_t active_write_sent_ms = this->write_sent_ms_;
    const uint32_t active_read_sent_ms = this->read_sent_ms_;
    const uint32_t active_write_generation = this->write_send_generation_;
    const uint32_t active_read_generation = this->read_send_generation_;
    this->request_id_ = request_id;
    this->target_ = enabled;
    this->observed_ = 0;
    this->observed_valid_ = false;
    this->exception_ = 0;
    this->write_sent_ms_ = 0;
    this->read_sent_ms_ = 0;
    this->write_send_generation_ = 0;
    this->read_send_generation_ = 0;
    this->publish_terminal_("NOT_QUEUED");
    this->request_id_ = active_id;
    this->target_ = active_target;
    this->observed_ = active_observed;
    this->observed_valid_ = active_observed_valid;
    this->exception_ = active_exception;
    this->write_sent_ms_ = active_write_sent_ms;
    this->read_sent_ms_ = active_read_sent_ms;
    this->write_send_generation_ = active_write_generation;
    this->read_send_generation_ = active_read_generation;
    this->publish_(pending_state);
    return;
  }
  if (this->active_ && request_id != "switch" && this->request_id_ == request_id && this->target_ != enabled) {
    // Reusing a live request_id with a different target is a payload conflict.
    const std::string active_id = this->request_id_;
    const bool active_target = this->target_;
    const Frame active_frame = this->frame_;
    this->request_id_ = request_id;
    this->target_ = enabled;
    this->publish_("REJECTED");
    this->request_id_ = active_id;
    this->target_ = active_target;
    this->publish_(active_frame == Frame::READBACK ? "ACKNOWLEDGED_WAITING_READBACK" : "ACCEPTED");
    return;
  }
  if (this->active_) {
    const bool old_sent = this->sent_;
    this->clear_tx_queue_for_device();
    // The pinned hub runs send_frame_ and on_sent synchronously in its loop. If this
    // request is handled with sent_ still false, no bytes were sent and the owner-scoped
    // silent clear retires its READY frame. An in-flight command remains uncertain.
    this->publish_terminal_(old_sent ? "OUTCOME_UNCERTAIN" : "CANCELED");
  }
  this->request_id_ = request_id;
  this->target_ = enabled;
  this->observed_ = 0;
  this->observed_valid_ = false;
  this->exception_ = 0;
  this->active_ = true;
  this->sent_ = false;
  this->write_sent_ms_ = 0;
  this->read_sent_ms_ = 0;
  this->write_send_generation_ = 0;
  this->read_send_generation_ = 0;
  this->frame_ = Frame::WRITE;
  this->publish_("ACCEPTED");
  if (!this->write_single_register(18, enabled ? 1 : 0)) {
    this->active_ = false;
    this->frame_ = Frame::NONE;
    this->publish_terminal_("NOT_QUEUED");
  }
}

void OutputOwner::observe_readback(uint16_t value) {
  // The periodic probe is a state mirror only. Never let it settle an active command;
  // APPLIED is reserved for the one-shot FC03 queued after the FC06 acknowledgement.
  if (this->active_) return;
  this->observed_ = value;
  this->observed_valid_ = true;
  this->publish_state((value & 1) != 0);
}

void OutputOwner::on_sent(std::span<const uint8_t> request_pdu) {
  if (!this->active_ || request_pdu.empty()) return;
  const uint8_t function_code = request_pdu[0];
  if ((this->frame_ == Frame::WRITE && function_code != 0x06) ||
      (this->frame_ == Frame::READBACK && function_code != 0x03)) return;
  // This callback marks actual transmission (not queue admission).
  const uint32_t sent_ms = millis();
  const uint32_t generation = ++this->send_generation_;
  if (this->frame_ == Frame::WRITE) {
    this->sent_ = true;
    this->write_sent_ms_ = sent_ms;
    this->write_send_generation_ = generation;
    this->publish_("ACCEPTED");
  } else {
    this->read_sent_ms_ = sent_ms;
    this->read_send_generation_ = generation;
    this->publish_("ACKNOWLEDGED_WAITING_READBACK");
  }
}

void OutputOwner::on_not_sent(std::span<const uint8_t> request_pdu) {
  if (!this->active_) return;
  if (this->frame_ == Frame::WRITE && !this->sent_) {
    this->active_ = false;
    this->frame_ = Frame::NONE;
    this->publish_terminal_("CANCELED");
    return;
  }
  // An address-scoped controller clear can retire an unsent FC03 read after the
  // write was already sent/ACKed. That is not a canceled physical write.
  this->uncertain_("owner frame retired before transmission");
}

bool OutputOwner::on_no_response(std::span<const uint8_t> request_pdu) {
  if (this->active_) this->uncertain_("no response; no retry");
  return false;
}

void OutputOwner::on_error(std::span<const uint8_t> request_pdu, modbus::ExceptionCode code) {
  if (!this->active_) return;
  this->exception_ = static_cast<uint8_t>(code);
  if (this->frame_ == Frame::WRITE && !request_pdu.empty() && request_pdu[0] == 0x06) {
    this->active_ = false;
    this->frame_ = Frame::NONE;
    this->publish_terminal_("REJECTED", "exception");
    return;
  }
  // A readback exception cannot reject a write already ACKed by FC06.
  this->uncertain_("R18 readback exception");
}

void OutputOwner::on_write_single_register(uint16_t address, uint16_t value,
                                           modbus::ResponseStatus status) {
  if (!this->active_ || address != 18 || this->frame_ != Frame::WRITE) return;
  if (status.has_value()) {
    this->exception_ = static_cast<uint8_t>(*status);
    this->active_ = false;
    this->frame_ = Frame::NONE;
    this->publish_terminal_("REJECTED", "exception");
    return;
  }
  if (value != (this->target_ ? 1 : 0)) {
    this->uncertain_("FC06 echo mismatch");
    return;
  }
  // FC06 echo is only an acknowledgement. It is not physical application evidence.
  this->frame_ = Frame::READBACK;
  this->publish_("ACKNOWLEDGED_WAITING_READBACK");
  if (!this->read_holding_registers(18, 1)) this->uncertain_("readback not queued");
}

void OutputOwner::on_read_holding_registers(uint16_t address, std::span<const uint16_t> values,
                                            modbus::ResponseStatus status) {
  if (!this->active_ || address != 18 || this->frame_ != Frame::READBACK) return;
  if (status.has_value() || values.size() != 1) {
    if (status.has_value()) this->exception_ = static_cast<uint8_t>(*status);
    this->uncertain_("readback failed");
    return;
  }
  this->observed_ = values[0];
  this->observed_valid_ = true;
  const bool actual = (values[0] & 1) != 0;
  this->active_ = false;
  this->frame_ = Frame::NONE;
  this->publish_terminal_(actual == this->target_ ? "APPLIED" : "OUTCOME_UNCERTAIN");
  this->publish_state(actual);
}
}  // namespace esphome::rd6018_output_owner
