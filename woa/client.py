"""Networking client for the K-Frame switcher."""

import socket
import time
import threading
import xml.etree.ElementTree as ET
from collections import defaultdict, OrderedDict
from typing import Any, Dict, List, Optional

class SimpleKFrameClient:
    """Simplified K-Frame Client - matches working CLI"""
    KFRAME_PORT = 2012
    HEARTBEAT_INTERVAL = 1.0  # 1 second like C implementation
    HEARTBEAT_INTERVAL_LONG = 5.0  # 5 seconds after data complete
    BUFFER_SIZE = 65536
    def __init__(self, host: str, port: int = KFRAME_PORT):
        self.host = host
        self.port = port
        self.socket = None
        self.connected = False
        # Simple data structures like CLI
        self.current_on_air = defaultdict(dict)  # suite -> me -> source_name
        self.source_names = {}  # source_id -> source_name
        self.on_air_layers = defaultdict(lambda: defaultdict(list))  # suite -> vpe -> [active layers]
        self.layer_sources = defaultdict(lambda: defaultdict(dict))  # suite -> vpe -> layer -> source_id
        self.aux_assignments = defaultdict(lambda: OrderedDict())  # suite -> aux outputs
        self.all_outputs = defaultdict(lambda: OrderedDict())  # suite -> all outputs
        self.engineering_sources = OrderedDict()
        self.logical_sources = defaultdict(lambda: OrderedDict())
        self.engineering_sources_ready = False
        self.logical_suites_ready = set()
        self.running = False
        self.lock = threading.Lock()
        self.gui = None
        self._initial_requests_sent = False
        self._update_callbacks = []
        # Heartbeat tracking like C implementation
        self.data_complete = False
        self.last_heartbeat_response = time.time()
        self.heartbeat_interval = self.HEARTBEAT_INTERVAL
        # Response timer tracking like C implementation
        self.response_timer = 0.0
        self.response_timer_start = 0.0
        self.RESPONSE_TIMEOUT = 4.0  # RXTIME = 4000ms in C code
    def connect(self) -> bool:
        """Connect to K-Frame - simple like CLI"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(4.0)  # Match C implementation RXTIME
            self.socket.connect((self.host, self.port))
            self.connected = True
            print(f"Connected to K-Frame at {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False

    def _send_initial_requests(self) -> bool:
        """Send the initial configuration requests once."""
        if self._initial_requests_sent:
            return True
        success = self.request_data()
        if success:
            self._initial_requests_sent = True
            self.send_heartbeat()
        return success

    def send_message(self, message: str) -> bool:
        """Send message - simple like CLI"""
        if not self.connected:
            return False
        try:
            self.socket.send(message.encode('utf-8'))
            return True
        except Exception as e:
            print(f"Send error: {e}")
            return False
    def authenticate(self) -> bool:
        """Send authentication - like CLI"""
        auth = """<ETP>
    <Authentication-Request>
        <Protocol>GV Ethernet Tally</Protocol>
        <ProtocolVersion>3.0</ProtocolVersion>
        <AppName>SimpleGUITallyReceiver</AppName>
        <AppVersion>1.0</AppVersion>
        <Suite>All</Suite>
    </Authentication-Request>
</ETP>
"""
        success = self.send_message(auth)
        if success:
            # Set response timer like C implementation
            self.response_timer_start = time.time()
            self.response_timer = self.RESPONSE_TIMEOUT
            print("Authentication sent (response timer set)")
        return success
    def request_data(self) -> bool:
        """Request data - like CLI - including missing TallySubscription"""
        requests = [
            "<ETP>\n<TallySubscription-Request/>\n</ETP>\n",  # MISSING FROM ORIGINAL
            "<ETP>\n<Configuration-Request/>\n</ETP>\n",
            "<ETP>\n<EngineeringSourceMap-Request/>\n</ETP>\n",
            "<ETP>\n<LogicalSourceMap-Request/>\n</ETP>\n",
            "<ETP>\n<VPEInputMap-Request/>\n</ETP>\n",
            "<ETP>\n<VPEOutputMap-Request/>\n</ETP>\n",
            "<ETP>\n<OutputTallyMap-Request/>\n</ETP>\n"
        ]
        for req in requests:
            if not self.send_message(req):
                return False
            time.sleep(0.05)  # Match C implementation delay
        return True
    def send_heartbeat(self) -> bool:
        """Send heartbeat - like CLI"""
        success = self.send_message("<ETP>\n<Heartbeat-Request/>\n</ETP>\n")
        if success:
            # Set response timer like C implementation
            self.response_timer_start = time.time()
            self.response_timer = self.RESPONSE_TIMEOUT
            print("Heartbeat sent (response timer set)")
        return success
    def process_xml_chunk(self, xml_text: str):
        """Simple processing like CLI"""
        try:
            # Simple string-based checks like CLI
            if '<VPEInputContribution' in xml_text:
                print("Processing VPEInputContribution...")
                self.process_vpe_input_simple(xml_text)
            elif '<VPEInputMap' in xml_text:
                print("Processing VPEInputMap...")
                self.process_vpe_input_simple(xml_text)
            elif '<EngineeringSourceMap' in xml_text:
                print("Processing EngineeringSourceMap...")
                self.process_engineering_source_map(xml_text)
            elif '<LogicalSourceMap' in xml_text:
                print("Processing LogicalSourceMap...")
                self.process_logical_source_map(xml_text)
            elif '<OutputTally' in xml_text:
                print("Processing OutputTally...")
                self.process_output_tally(xml_text)
            elif '<VPEOutputContribution' in xml_text:
                print("Processing VPEOutputContribution...")
                self.process_vpe_output_layers(xml_text)
            elif '<SetComplete/>' in xml_text:
                print("Data set complete")
                self.data_complete = True
                # Switch to longer heartbeat interval like C implementation
                self.heartbeat_interval = self.HEARTBEAT_INTERVAL_LONG
                self.trigger_gui_update()
            elif '<Heartbeat>' in xml_text:
                # Handle heartbeat response like C implementation
                self.last_heartbeat_response = time.time()
                self.response_timer = 0.0  # Clear response timer
                print("Heartbeat response received (response timer cleared)")
            elif '<Authentication>' in xml_text:
                # Handle authentication response
                self.response_timer = 0.0  # Clear response timer
                print("Authentication response received (response timer cleared)")
                self._send_initial_requests()
        except Exception as e:
            print(f"Parse error: {e}")
    def process_vpe_input_simple(self, xml_text: str):
        """Extract source IDs from VPE inputs like CLI"""
        try:
            # Extract suite number first
            suite_start = xml_text.find('Suite="')
            if suite_start > 0:
                suite_start += len('Suite="')
                suite_end = xml_text.find('"', suite_start)
                if suite_end > 0:
                    suite_num = int(xml_text[suite_start:suite_end])
                    suite_index = suite_num - 1  # Suite 1 → index 0, Suite 2 → index 1
                else:
                    suite_index = 0  # fallback
            else:
                suite_index = 0  # fallback
            # Extract VPE sections and their BkgdA assignments
            vpe_sections = xml_text.split('<VPE Name="')
            for section in vpe_sections[1:]:  # Skip first empty split
                vpe_end = section.find('"')
                if vpe_end > 0:
                    vpe_name = section[:vpe_end]
                    # Store all layer source assignments for this VPE
                    with self.lock:
                        # Store key sources
                        for key_num in range(1, 7):
                            key_fill = f'<Input Name="key{key_num}-fill">'
                            if key_fill in section:
                                key_start = section.find(key_fill) + len(key_fill)
                                key_end = section.find('</Input>', key_start)
                                if key_end > key_start:
                                    key_source = section[key_start:key_end].strip()
                                    self.layer_sources[suite_index][vpe_name][f'key{key_num}-fill'] = key_source
                        # Store background sources (all background layers)
                        background_layers = ['BkgdA', 'BkgdB', 'BkgdC', 'BkgdD', 'BkgdU1', 'BkgdU2']
                        for bkgd_layer in background_layers:
                            bkgd_start_tag = f'<Input Name="{bkgd_layer}">'
                            if bkgd_start_tag in section:
                                bkgd_start = section.find(bkgd_start_tag) + len(bkgd_start_tag)
                                bkgd_end = section.find('</Input>', bkgd_start)
                                if bkgd_end > bkgd_start:
                                    bkgd_source = section[bkgd_start:bkgd_end].strip()
                                    self.layer_sources[suite_index][vpe_name][bkgd_layer] = bkgd_source
                    # Check if VPE is acquired
                    acquired_start = section.find('Acquired="')
                    if acquired_start > 0:
                        acquired_start += len('Acquired="')
                        acquired_end = section.find('"', acquired_start)
                        if acquired_end > 0:
                            is_acquired = section[acquired_start:acquired_end] == "True"
                        else:
                            is_acquired = False
                    else:
                        is_acquired = False
                    # Only process acquired VPEs
                    if is_acquired:
                        # Look for BkgdA assignment in this VPE
                        bkgd_start = section.find('<Input Name="BkgdA">')
                        if bkgd_start > 0:
                            bkgd_start += len('<Input Name="BkgdA">')
                            bkgd_end = section.find('</Input>', bkgd_start)
                            if bkgd_end > 0:
                                source_id = section[bkgd_start:bkgd_end].strip()
                                # Store source ID for this VPE using correct suite
                                with self.lock:
                                    if source_id:
                                        # Look up source name, show layer and source name with number
                                        if source_id in self.source_names:
                                            display_name = f"BKGD A: {self.source_names[source_id]} ({source_id})"
                                        else:
                                            display_name = f"BKGD A: Source {source_id}"
                                        self.current_on_air[suite_index][vpe_name] = display_name
                                    else:
                                        self.current_on_air[suite_index][vpe_name] = "BKGD A: NO SOURCE"
                    else:
                        # VPE is not acquired
                        with self.lock:
                            self.current_on_air[suite_index][vpe_name] = "Not Allocated"
            # After updating layer sources, refresh display for VPEs that already have active layer data
            for suite_idx in range(4):
                for vpe_name in self.on_air_layers[suite_idx]:
                    if self.on_air_layers[suite_idx][vpe_name]:  # If this VPE has active layers
                        self.update_vpe_display(suite_idx, vpe_name)
            self.trigger_gui_update()
        except Exception as e:
            print(f"VPE input parse error: {e}")
    def process_output_tally(self, xml_text: str):
        """Parse OutputTally messages to capture aux and output assignments."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            print(f"OutputTally parse error: {exc}")
            return
        tally = root.find('OutputTally')
        if tally is None:
            return
        tally_type = tally.findtext('Type') or ''
        is_full = tally_type.strip().lower() == 'full'
        updates_by_suite = defaultdict(lambda: OrderedDict())
        outputs_by_suite = defaultdict(lambda: OrderedDict())
        for output_elem in tally.findall('Output'):
            name = (output_elem.attrib.get('Name') or '').strip()
            suite_attr = output_elem.attrib.get('Suite')
            try:
                suite_index = int(suite_attr) - 1 if suite_attr else 0
            except (TypeError, ValueError):
                suite_index = 0
            out_num_attr = output_elem.attrib.get('OutNum')
            try:
                out_num = int(out_num_attr) if out_num_attr else None
            except (TypeError, ValueError):
                out_num = None
            if out_num is None:
                continue
            logsrc = (output_elem.attrib.get('LogSrc') or '').strip()
            outputs_by_suite[suite_index][out_num] = {
                'name': name,
                'logsrc': logsrc,
            }
            if name and 'aux' in name.lower():
                updates_by_suite[suite_index][out_num] = {
                    'name': name,
                    'logsrc': logsrc,
                }
        with self.lock:
            for suite_index, outputs in outputs_by_suite.items():
                if is_full or suite_index not in self.all_outputs:
                    current = OrderedDict()
                else:
                    current = OrderedDict(self.all_outputs[suite_index])
                for out_num, data in sorted(outputs.items()):
                    current[out_num] = data
                self.all_outputs[suite_index] = current
            for suite_index, aux_updates in updates_by_suite.items():
                if is_full:
                    self.aux_assignments[suite_index].clear()
                suite_aux = self.aux_assignments[suite_index]
                for out_num, data in sorted(aux_updates.items()):
                    suite_aux[out_num] = data
        self.trigger_gui_update()
    def process_vpe_output_layers(self, xml_text: str):
        """Parse VPEOutputContribution to detect which layers are on-air"""
        try:
            # Extract suite number
            suite_start = xml_text.find('Suite="')
            if suite_start > 0:
                suite_start += len('Suite="')
                suite_end = xml_text.find('"', suite_start)
                if suite_end > 0:
                    suite_num = int(xml_text[suite_start:suite_end])
                    suite_index = suite_num - 1
                else:
                    suite_index = 0
            else:
                suite_index = 0
            # Extract VPE sections
            vpe_sections = xml_text.split('<VPE Name="')
            for section in vpe_sections[1:]:
                vpe_end = section.find('"')
                if vpe_end > 0:
                    vpe_name = section[:vpe_end]
                    # Check if VPE is acquired
                    if 'Acquired="True"' in section:
                        # Look for PgmA output (what's on-air)
                        pgm_start = section.find('<Output Name="PgmA">')
                        if pgm_start > 0:
                            pgm_end = section.find('</Output>', pgm_start)
                            if pgm_end > 0:
                                pgm_section = section[pgm_start:pgm_end]
                                # Extract all active layers
                                active_layers = []
                                inputs = pgm_section.split('<Input>')
                                for input_data in inputs[1:]:  # Skip first empty split
                                    input_end = input_data.find('</Input>')
                                    if input_end > 0:
                                        layer_name = input_data[:input_end].strip()
                                        active_layers.append(layer_name)
                                # Store active layers for this VPE
                                with self.lock:
                                    self.on_air_layers[suite_index][vpe_name] = active_layers
                                    # Now combine with source assignments to create display
                                    self.update_vpe_display(suite_index, vpe_name)
            self.trigger_gui_update()
        except Exception as e:
            print(f"VPE output layers parse error: {e}")
    def update_vpe_display(self, suite_index, vpe_name):
        """Combine layer and source data to create display text"""
        try:
            # Don't update during initial loading if we don't have source names yet
            if not self.source_names:
                return
            active_layers = self.on_air_layers[suite_index].get(vpe_name, [])
            layer_sources = self.layer_sources[suite_index].get(vpe_name, {})
            # Separate keyers and backgrounds for proper ordering
            keyer_parts = []
            background_parts = []
            for layer in active_layers:
                # Map layer names
                if layer.startswith('Bkgd'):
                    # Handle all background layers: BkgdA, BkgdB, BkgdC, BkgdD, BkgdU1, BkgdU2
                    if layer == 'BkgdA':
                        layer_display = 'BKGD A'
                    elif layer == 'BkgdB':
                        layer_display = 'BKGD B'
                    elif layer == 'BkgdC':
                        layer_display = 'BKGD C'
                    elif layer == 'BkgdD':
                        layer_display = 'BKGD D'
                    elif layer == 'BkgdU1':
                        layer_display = 'BKGD U1'
                    elif layer == 'BkgdU2':
                        layer_display = 'BKGD U2'
                    else:
                        layer_display = f'BKGD {layer[4:]}'  # Generic fallback
                elif 'key' in layer.lower():
                    # Extract key number from key1-fill, key1-cut, etc.
                    if '-fill' in layer:
                        key_num = layer.replace('key', '').replace('-fill', '')
                        layer_display = f'KEY {key_num}'
                    else:
                        continue  # Skip cut layers in display
                else:
                    continue
                # Get source for this layer
                source_id = layer_sources.get(layer.replace('-fill', '').replace('-cut', ''))
                if not source_id:
                    # Try to get from stored input data
                    source_id = layer_sources.get(layer)
                if source_id and source_id in self.source_names:
                    source_text = f"{layer_display}: {self.source_names[source_id]} ({source_id})"
                elif source_id:
                    source_text = f"{layer_display}: Source {source_id}"
                else:
                    source_text = f"{layer_display}: No Source"
                # Add to appropriate list based on layer type (no manual formatting needed)
                if 'key' in layer.lower():
                    keyer_parts.append(source_text)
                else:
                    background_parts.append(source_text)
            # Update display - keyers first, then backgrounds, each on separate line
            all_parts = []
            # Sort keyer parts by key number for consistent ordering
            keyer_parts.sort(key=lambda x: int(x.split('KEY ')[1].split(':')[0]) if 'KEY ' in x else 0)
            # Add keyers first
            all_parts.extend(keyer_parts)
            # Add separator line if we have both keyers and backgrounds
            if keyer_parts and background_parts:
                all_parts.append("─────────────")
            # Add backgrounds after keyers
            all_parts.extend(background_parts)
            if all_parts:
                self.current_on_air[suite_index][vpe_name] = "\n".join(all_parts)
        except Exception as e:
            print(f"Update VPE display error: {e}")
    def process_logical_source_map(self, xml_text: str):
        """Extract logical sources and map to engineering IDs."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            print(f"LogicalSourceMap parse error: {exc}")
            return
        logical = root.find('LogicalSourceMap')
        if logical is None:
            return
        suite_attr = logical.get('Suite') or logical.get('suite') or '1'
        try:
            suite_index = max(0, int(suite_attr) - 1)
        except (TypeError, ValueError):
            suite_index = 0
        map_type = (logical.findtext('Type') or '').strip().lower()
        entries = OrderedDict()
        for logsrc in logical.findall('LogSrc'):
            log_id = (logsrc.get('ID') or '').strip()
            name = (logsrc.findtext('Name') or logsrc.get('Name') or '').strip()
            src_type = (logsrc.get('Type') or '').strip()
            vsources = []
            for vs in logsrc.findall('VSrc'):
                vsources.append({
                    'id': (vs.text or '').strip(),
                    'stype': (vs.get('SType') or '').strip(),
                })
            entries[log_id] = {
                'id': log_id,
                'name': name,
                'type': src_type,
                'vsources': vsources,
            }
        with self.lock:
            existing_entries = self.logical_sources.get(suite_index, OrderedDict())
            is_full = map_type in ('full', 'complete')
            if is_full:
                logical_map = entries
            else:
                logical_map = OrderedDict(existing_entries)
                for log_id, data in entries.items():
                    logical_map[log_id] = data
            self.logical_sources[suite_index] = logical_map
            if logical_map:
                self.logical_suites_ready.add(suite_index)
            else:
                self.logical_suites_ready.discard(suite_index)
            if is_full:
                removed_ids = set(existing_entries.keys()) - set(logical_map.keys())
                for removed_id in removed_ids:
                    self.source_names.pop(removed_id, None)
            for log_id, data in entries.items():
                if data['name']:
                    self.source_names[log_id] = data['name']
        try:
            for suite_idx in range(4):
                for vpe_name in self.on_air_layers[suite_idx]:
                    if self.on_air_layers[suite_idx][vpe_name]:
                        self.update_vpe_display(suite_idx, vpe_name)
        except Exception as exc:
            print(f"Update VPE display error after logical map: {exc}")

    def process_engineering_source_map(self, xml_text: str):
        """Capture engineering source definitions."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            print(f"EngineeringSourceMap parse error: {exc}")
            return
        eng_map = root.find('EngineeringSourceMap')
        if eng_map is None:
            return
        map_type = (eng_map.get('Type') or '').strip().lower()
        entries = OrderedDict()
        for eng_src in eng_map.findall('EngSrc'):
            eng_id = (eng_src.get('ID') or '').strip()
            name = (eng_src.get('Name') or eng_src.findtext('Name') or '').strip()
            src_type = (eng_src.get('Type') or '').strip()
            bnc_elem = eng_src.find('BNC_V')
            bnc = bnc_elem.text.strip() if bnc_elem is not None and bnc_elem.text else ''
            entries[eng_id] = {
                'id': eng_id,
                'name': name,
                'type': src_type,
                'bnc': bnc,
            }
        with self.lock:
            existing = getattr(self, 'engineering_sources', OrderedDict())
            is_full = map_type in ('full', 'complete')
            if is_full:
                merged = OrderedDict(entries)
            else:
                merged = OrderedDict(existing)
                for eng_id, data in entries.items():
                    merged[eng_id] = data
            self.engineering_sources = merged
            self.engineering_sources_ready = bool(merged)
        self.trigger_gui_update()
    def register_update_callback(self, callback):
        """Register a callable that fires when fresh data arrives."""
        if not callable(callback):
            return
        with self.lock:
            if callback not in self._update_callbacks:
                self._update_callbacks.append(callback)

    def unregister_update_callback(self, callback):
        """Remove a previously registered update callback."""
        with self.lock:
            if callback in self._update_callbacks:
                self._update_callbacks.remove(callback)

    def _notify_update_callbacks(self):
        with self.lock:
            callbacks = list(self._update_callbacks)
        for callback in callbacks:
            try:
                callback()
            except Exception as exc:
                print(f"Update callback failed: {exc}")

    def trigger_gui_update(self):
        """Trigger GUI update"""
        if hasattr(self, 'gui') and self.gui:
            self.gui.root.after_idle(self.gui.update_display)
        self._notify_update_callbacks()
    def receive_worker(self):
        """Simple receive worker like CLI"""
        buffer = ""
        while self.running:
            try:
                data = self.socket.recv(self.BUFFER_SIZE)
                if not data:
                    break
                buffer += data.decode('utf-8', errors='ignore')
                # Process complete ETP documents
                while '</ETP>' in buffer:
                    end_pos = buffer.find('</ETP>') + 6
                    xml_chunk = buffer[:end_pos]
                    buffer = buffer[end_pos:]
                    self.process_xml_chunk(xml_chunk)
                # Prevent buffer overflow
                if len(buffer) > 1000000:
                    buffer = ""
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Receive error: {e}")
                break
    def heartbeat_worker(self):
        """Adaptive heartbeat worker like C implementation"""
        while self.running:
            time.sleep(self.heartbeat_interval)
            if self.running:
                # Check response timer like C implementation
                if self.response_timer > 0.0:
                    elapsed = time.time() - self.response_timer_start
                    if elapsed >= self.response_timer:
                        print(f"Response timeout after {elapsed:.1f}s - connection may be lost")
                        self.response_timer = 0.0
                        # Could implement reconnection logic here like C code
                success = self.send_heartbeat()
                if success:
                    print(f"Heartbeat sent (interval: {self.heartbeat_interval}s)")
                else:
                    print("Heartbeat send failed")
    def start(self) -> bool:
        """Simple start like CLI - synchronous"""
        if not self.connect():
            return False
        self.running = True
        # Start threads like CLI
        threading.Thread(target=self.receive_worker, daemon=True).start()
        threading.Thread(target=self.heartbeat_worker, daemon=True).start()
        # Synchronous registration like CLI
        print("Starting registration...")
        if not self.authenticate():
            return False
        if not self._send_initial_requests():
            time.sleep(0.25)
            if not self._send_initial_requests():
                return False
        print("Registration complete")
        return True
    def stop(self):
        """Simple stop like CLI"""
        self.running = False
        self._initial_requests_sent = False
        if self.socket:
            self.socket.close()
        print("Client stopped")
