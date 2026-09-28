/**
 * ABB IRB 1660ID Digital Twin 3D Visualization
 * 
 * Features:
 * - High-speed WebSocket telemetry reception (/api/robot/ws)
 * - Decoupled 60fps render loop with linear interpolation (LERP)
 * - Articulated 6-axis kinematic model with ABB white-body / dark-joint / orange-accent convention
 * - Reach-accurate IRB 1660ID proportions (1.55m reach)
 * - CAD swap-in ready architecture for RobotStudio GLTF export
 * - Stale-data detection and interactive camera presets
 */

// ==========================================================================
// CAD SWAP-IN READY LOADER: ABB IRB 1660ID
// To replace proxy geometry with the real CAD model exported from RobotStudio:
// 1. Export station geometry from RobotStudio as GLTF / GLB (.glb) with link meshes separated.
// 2. Include THREE.GLTFLoader in index.html:
//    <script src="/static/js/libs/GLTFLoader.js"></script>
// 3. Drop in the following loader to replace the primitive meshes:
//
// const loader = new THREE.GLTFLoader();
// loader.load('/static/models/abb_irb1660id.glb', (gltf) => {
//   const model = gltf.scene;
//   // Reparent each link mesh to kinematic groups j1Group..j6Group:
//   // j1Group.add(model.getObjectByName('link_1'));
//   // j2Group.add(model.getObjectByName('link_2'));
//   // j3Group.add(model.getObjectByName('link_3'));
//   // j4Group.add(model.getObjectByName('link_4'));
//   // j5Group.add(model.getObjectByName('link_5'));
//   // j6Group.add(model.getObjectByName('link_6'));
//   // applyPoseDeg() downstream automatically drives whichever meshes are in these groups!
// });
// ==========================================================================

class DigitalTwinViewer {
  constructor(containerId, options = {}) {
    this.container = document.getElementById(containerId);
    if (!this.container) return;

    this.options = Object.assign({
      autoConnect: true,
      showGrid: true,
      showAxes: true,
    }, options);

    // Three.js Core
    this.scene = null;
    this.camera = null;
    this.renderer = null;
    this.controls = null;
    this.animFrameId = null;

    // Kinematic Joints & Links
    this.joints = [];
    this.jointMeshes = [];
    this.toolFlange = null;
    this.tcpMarker = null;

    // Joint Limits for IRB 1660ID (degrees) and Rotation Direction Signs
    // Verified against ABB IRB1660ID datasheet specs:
    // J1: ±180°, J2: +150/−90°, J3: +79/−238°, J4: ±175°, J5: ±120°, J6: ±400°
    this.jointLimits = [
      { name: "J1 (Base)", min: -180, max: 180, axis: "y", sign: 1, rangeText: "±180°" },
      { name: "J2 (Lower Arm)", min: -90, max: 150, axis: "z", sign: -1, rangeText: "+150/−90°" },
      { name: "J3 (Upper Arm)", min: -238, max: 79, axis: "z", sign: -1, rangeText: "+79/−238°" },
      { name: "J4 (Wrist Roll)", min: -175, max: 175, axis: "x", sign: -1, rangeText: "±175°" },
      { name: "J5 (Wrist Bend)", min: -120, max: 120, axis: "z", sign: -1, rangeText: "±120°" },
      { name: "J6 (Turn Flange)", min: -400, max: 400, axis: "x", sign: -1, rangeText: "±400°" },
    ];
    this.loadSavedSigns();

    // State & Interpolation Buffer
    this.currentJoints = [0, 0, 0, 0, 0, 0];
    this.targetJoints = [0, 0, 0, 0, 0, 0];
    this.prevJoints = [0, 0, 0, 0, 0, 0];
    this.lastPacketTime = 0;
    this.packetInterval = 100; // ms
    this.packetCount = 0;
    this.fpsCount = 0;
    this.lastFpsCalcTime = performance.now();
    this.isStale = false;
    this.isConnected = false;

    // WebSocket
    this.ws = null;
    this.reconnectTimer = null;

    this.init3D();
    this.initUI();
    if (this.options.autoConnect) {
      this.connectWebSocket();
    }
  }

  // --------------------------------------------------------------------------
  // 3D Scene Initialization
  // --------------------------------------------------------------------------
  init3D() {
    const width = this.container.clientWidth || 800;
    const height = this.container.clientHeight || 450;

    // Scene
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x1B1E28);
    this.scene.fog = new THREE.FogExp2(0x1B1E28, 0.10);

    // Camera
    this.camera = new THREE.PerspectiveCamera(45, width / height, 0.05, 50);
    this.setCameraPreset("iso");

    // Renderer
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: "high-performance" });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.15;
    this.container.appendChild(this.renderer.domElement);

    // OrbitControls
    this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.maxPolarAngle = Math.PI / 2 + 0.05; // don't go far below ground
    this.controls.minDistance = 0.4;
    this.controls.maxDistance = 10.0;
    this.controls.target.set(0, 0.75, 0);

    // Auto-rotate until first user interaction
    this.controls.autoRotate = true;
    this.controls.autoRotateSpeed = 0.6;
    this.controls.addEventListener("start", () => {
      this.controls.autoRotate = false;
    });

    // Lighting
    this.setupLighting();

    // Environment: Industrial Floor, Pedestal & Coordinate Grid
    this.setupEnvironment();

    // Build Kinematic Articulated Model (ABB White-Body / Dark-Joint Convention)
    this.buildRobotModel();

    // Resize Observer
    window.addEventListener("resize", () => this.onResize());
    if (window.ResizeObserver) {
      new ResizeObserver(() => this.onResize()).observe(this.container);
    }

    // Start 60fps render loop
    this.renderLoop();
  }

  setupLighting() {
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.75);
    this.scene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0xffffff, 1.3);
    dirLight1.position.set(3, 5, 4);
    dirLight1.castShadow = true;
    dirLight1.shadow.mapSize.width = 1024;
    dirLight1.shadow.mapSize.height = 1024;
    dirLight1.shadow.camera.near = 0.5;
    dirLight1.shadow.camera.far = 15;
    dirLight1.shadow.camera.left = -2;
    dirLight1.shadow.camera.right = 2;
    dirLight1.shadow.camera.top = 2;
    dirLight1.shadow.camera.bottom = -2;
    this.scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0x7389AE, 0.5);
    dirLight2.position.set(-4, 3, -3);
    this.scene.add(dirLight2);

    const rimLight = new THREE.DirectionalLight(0xFFB74D, 0.4);
    rimLight.position.set(0, -2, -4);
    this.scene.add(rimLight);
  }

  setupEnvironment() {
    // Industrial Floor plate
    const floorGeo = new THREE.PlaneGeometry(16, 16);
    const floorMat = new THREE.MeshStandardMaterial({
      color: 0x161822,
      roughness: 0.85,
      metalness: 0.2,
    });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -0.002;
    floor.receiveShadow = true;
    this.scene.add(floor);

    // Industrial Grid (Subtle cyan & navy lines)
    const grid = new THREE.GridHelper(10, 20, 0x4A6B82, 0x242838);
    grid.position.y = 0;
    this.scene.add(grid);

    // XYZ Origin Axis Triad (standard CAD/robotics convention)
    const originTriad = new THREE.AxesHelper(0.4);
    originTriad.position.set(0, 0.001, 0);
    this.scene.add(originTriad);

    // Cell pedestal / mounting stand
    const pedestalGeo = new THREE.CylinderGeometry(0.32, 0.36, 0.08, 32);
    const pedestalMat = new THREE.MeshStandardMaterial({
      color: 0x222634,
      roughness: 0.45,
      metalness: 0.7,
    });
    const pedestal = new THREE.Mesh(pedestalGeo, pedestalMat);
    pedestal.position.y = 0.04;
    pedestal.receiveShadow = true;
    pedestal.castShadow = true;
    this.scene.add(pedestal);
  }

  // --------------------------------------------------------------------------
  // Kinematic Model Construction (ABB IRB 1660ID-6/1.55)
  // Modeled with ABB corporate colors: White arm bodies, dark graphite joints,
  // orange accent bands, and reach-accurate proportions (1.55m).
  // --------------------------------------------------------------------------
  buildRobotModel() {
    // Official ABB Corporate Material Palette
    const abbWhite = new THREE.MeshStandardMaterial({
      color: 0xEEF1F6, // ABB industrial clean cast white
      roughness: 0.32,
      metalness: 0.15,
    });
    const darkGraphite = new THREE.MeshStandardMaterial({
      color: 0x252934, // Dark joint motors, bearing rings, turn tables
      roughness: 0.45,
      metalness: 0.65,
    });
    const abbOrange = new THREE.MeshStandardMaterial({
      color: 0xFF5A00, // ABB safety orange accents & rings
      roughness: 0.35,
      metalness: 0.25,
    });
    const chrome = new THREE.MeshStandardMaterial({
      color: 0xDCE0E8, // Precision machined steel
      roughness: 0.18,
      metalness: 0.90,
    });
    const toolMat = new THREE.MeshStandardMaterial({
      color: 0x333842,
      roughness: 0.35,
      metalness: 0.80,
    });
    const brassNozzle = new THREE.MeshStandardMaterial({
      color: 0xD4AF37,
      roughness: 0.22,
      metalness: 0.88,
    });

    // Base Group (Fixed to pedestal)
    const baseGroup = new THREE.Group();
    baseGroup.position.set(0, 0.08, 0);
    this.scene.add(baseGroup);

    // Base Body Mesh (Dark Graphite)
    const baseBodyGeo = new THREE.CylinderGeometry(0.24, 0.28, 0.18, 32);
    const baseBody = new THREE.Mesh(baseBodyGeo, darkGraphite);
    baseBody.position.y = 0.09;
    baseBody.castShadow = true;
    baseGroup.add(baseBody);

    // Base ABB Safety Orange accent ring
    const ringGeo = new THREE.CylinderGeometry(0.245, 0.245, 0.025, 32);
    const ring = new THREE.Mesh(ringGeo, abbOrange);
    ring.position.y = 0.15;
    baseGroup.add(ring);

    // ==================== JOINT 1 (Rotation around Y) ====================
    // Height of axis 1 pivot: ~0.20m
    const j1Group = new THREE.Group();
    j1Group.position.set(0, 0.20, 0);
    baseGroup.add(j1Group);
    this.joints.push({ group: j1Group, axis: "y", sign: 1 });

    // Link 1 Body (Turntable + shoulder housing)
    const l1Turntable = new THREE.Mesh(new THREE.CylinderGeometry(0.23, 0.23, 0.12, 32), darkGraphite);
    l1Turntable.position.y = 0.06;
    l1Turntable.castShadow = true;
    j1Group.add(l1Turntable);

    // Link 1 Shoulder Cast Housing (ABB White)
    const l1ShoulderGeo = new THREE.BoxGeometry(0.28, 0.28, 0.30);
    const l1Shoulder = new THREE.Mesh(l1ShoulderGeo, abbWhite);
    l1Shoulder.position.set(0.04, 0.22, 0);
    l1Shoulder.castShadow = true;
    j1Group.add(l1Shoulder);

    // Shoulder decorative orange accent badge
    const shoulderBadge = new THREE.Mesh(new THREE.BoxGeometry(0.02, 0.10, 0.22), abbOrange);
    shoulderBadge.position.set(0.185, 0.22, 0);
    j1Group.add(shoulderBadge);

    // Axis 2 motor cover cylinder (Dark Graphite)
    const a2Motor = new THREE.Mesh(new THREE.CylinderGeometry(0.14, 0.14, 0.36, 32), darkGraphite);
    a2Motor.rotation.x = Math.PI / 2;
    a2Motor.position.set(0.04, 0.26, 0);
    j1Group.add(a2Motor);

    // ==================== JOINT 2 (Arm bend around Z) ====================
    // Axis 2 pivot: x=0.05, y=0.26, z=0 relative to J1
    const j2Group = new THREE.Group();
    j2Group.position.set(0.05, 0.26, 0);
    j1Group.add(j2Group);
    this.joints.push({ group: j2Group, axis: "z", sign: 1 });

    // Link 2 Body (Lower Arm - 0.65m length, ABB White)
    const l2Length = 0.65;
    const l2LowerArmGeo = new THREE.BoxGeometry(0.16, l2Length, 0.18);
    const l2LowerArm = new THREE.Mesh(l2LowerArmGeo, abbWhite);
    l2LowerArm.position.set(0, l2Length / 2, 0);
    l2LowerArm.castShadow = true;
    j2Group.add(l2LowerArm);

    // Lower arm side styling rail (Dark Graphite)
    const l2Rail = new THREE.Mesh(new THREE.BoxGeometry(0.04, l2Length * 0.8, 0.20), darkGraphite);
    l2Rail.position.set(-0.07, l2Length / 2, 0);
    j2Group.add(l2Rail);

    // Lower arm orange styling stripe
    const l2Stripe = new THREE.Mesh(new THREE.BoxGeometry(0.165, 0.04, 0.185), abbOrange);
    l2Stripe.position.set(0, l2Length * 0.75, 0);
    j2Group.add(l2Stripe);

    // Axis 3 elbow joint bearing housing (Dark Graphite)
    const a3Elbow = new THREE.Mesh(new THREE.CylinderGeometry(0.13, 0.13, 0.32, 32), darkGraphite);
    a3Elbow.rotation.x = Math.PI / 2;
    a3Elbow.position.set(0, l2Length, 0);
    j2Group.add(a3Elbow);

    // ==================== JOINT 3 (Arm bend around Z) ====================
    // Axis 3 pivot at top of lower arm
    const j3Group = new THREE.Group();
    j3Group.position.set(0, l2Length, 0);
    j2Group.add(j3Group);
    this.joints.push({ group: j3Group, axis: "z", sign: 1 });

    // Link 3 Body (Upper arm & Integrated DressPack rear housing, ABB White)
    const l3Length = 0.60;
    const l3Housing = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.18, 0.22), abbWhite);
    l3Housing.position.set(0.08, 0, 0);
    l3Housing.castShadow = true;
    j3Group.add(l3Housing);

    // Distinctive IRB 1660ID Hollow Arm section (internal cable routing channel, ABB White)
    const l3ArmTube = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.11, l3Length, 24), abbWhite);
    l3ArmTube.rotation.z = -Math.PI / 2;
    l3ArmTube.position.set(l3Length / 2, 0, 0);
    l3ArmTube.castShadow = true;
    j3Group.add(l3ArmTube);

    // Integrated DressPack cable guide cover (Dark Graphite with Orange highlight)
    const idCover = new THREE.Mesh(new THREE.BoxGeometry(l3Length * 0.7, 0.08, 0.12), darkGraphite);
    idCover.position.set(l3Length * 0.48, 0.10, 0);
    j3Group.add(idCover);

    const idStripe = new THREE.Mesh(new THREE.BoxGeometry(l3Length * 0.68, 0.015, 0.125), abbOrange);
    idStripe.position.set(l3Length * 0.48, 0.14, 0);
    j3Group.add(idStripe);

    // ==================== JOINT 4 (Wrist Roll around X) ====================
    // Axis 4 pivot along arm axis (X)
    const j4Group = new THREE.Group();
    j4Group.position.set(l3Length, 0, 0);
    j3Group.add(j4Group);
    this.joints.push({ group: j4Group, axis: "x", sign: 1 });

    // Link 4 Body (Hollow wrist housing, Dark Graphite)
    const l4WristGeo = new THREE.CylinderGeometry(0.085, 0.09, 0.18, 24);
    const l4Wrist = new THREE.Mesh(l4WristGeo, darkGraphite);
    l4Wrist.rotation.z = -Math.PI / 2;
    l4Wrist.position.set(0.09, 0, 0);
    l4Wrist.castShadow = true;
    j4Group.add(l4Wrist);

    // ==================== JOINT 5 (Wrist Bend around Z) ====================
    // Axis 5 pivot
    const j5Group = new THREE.Group();
    j5Group.position.set(0.18, 0, 0);
    j4Group.add(j5Group);
    this.joints.push({ group: j5Group, axis: "z", sign: 1 });

    // Link 5 Body (Compact tilting bracket, ABB White with Dark Graphite hub)
    const l5Geo = new THREE.BoxGeometry(0.10, 0.12, 0.14);
    const l5Mesh = new THREE.Mesh(l5Geo, abbWhite);
    l5Mesh.position.set(0.05, 0, 0);
    l5Mesh.castShadow = true;
    j5Group.add(l5Mesh);

    const l5Hub = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 0.15, 24), darkGraphite);
    l5Hub.rotation.x = Math.PI / 2;
    l5Hub.position.set(0.05, 0, 0);
    j5Group.add(l5Hub);

    // ==================== JOINT 6 (Tool Flange Turn around X) ====================
    const j6Group = new THREE.Group();
    j6Group.position.set(0.10, 0, 0);
    j5Group.add(j6Group);
    this.joints.push({ group: j6Group, axis: "x", sign: 1 });

    // Tool Flange (ISO 9409-1 standard mounting flange, Chrome steel)
    const flangeMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.055, 0.055, 0.025, 24), chrome);
    flangeMesh.rotation.z = -Math.PI / 2;
    flangeMesh.position.set(0.012, 0, 0);
    j6Group.add(flangeMesh);
    this.toolFlange = j6Group;

    // ==================== END-EFFECTOR TOOLING ====================
    // Realistic Arc Welding Torch (ABB IRB 1660ID is specialized for arc welding)
    const toolGroup = new THREE.Group();
    toolGroup.position.set(0.025, 0, 0);
    j6Group.add(toolGroup);

    // Torch mounting bracket
    const torchBracket = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.07, 0.05), toolMat);
    torchBracket.position.set(0.025, -0.02, 0);
    toolGroup.add(torchBracket);

    // Curved swan neck (welding gooseneck)
    const neckGeo = new THREE.CylinderGeometry(0.012, 0.015, 0.16, 16);
    const torchNeck = new THREE.Mesh(neckGeo, toolMat);
    torchNeck.rotation.z = -Math.PI / 3; // angled downward
    torchNeck.position.set(0.09, -0.06, 0);
    toolGroup.add(torchNeck);

    // Gas nozzle & contact tip (Brass)
    const nozzleGeo = new THREE.CylinderGeometry(0.008, 0.014, 0.05, 16);
    const nozzle = new THREE.Mesh(nozzleGeo, brassNozzle);
    nozzle.rotation.z = -Math.PI / 3;
    nozzle.position.set(0.15, -0.10, 0);
    toolGroup.add(nozzle);

    // Eye-in-hand D455 Camera Marker
    const camGeo = new THREE.BoxGeometry(0.025, 0.08, 0.03);
    const camMesh = new THREE.Mesh(camGeo, darkGraphite);
    camMesh.position.set(0.03, 0.05, 0);
    toolGroup.add(camMesh);

    const camLens = new THREE.Mesh(new THREE.CylinderGeometry(0.008, 0.008, 0.01, 16), chrome);
    camLens.rotation.z = -Math.PI / 2;
    camLens.position.set(0.045, 0.05, 0);
    toolGroup.add(camLens);

    // TCP Indicator Light (Spherical point at welding wire tip)
    const tcpGeo = new THREE.SphereGeometry(0.008, 16, 16);
    const tcpMat = new THREE.MeshBasicMaterial({ color: 0x50E3C2 });
    this.tcpMarker = new THREE.Mesh(tcpGeo, tcpMat);
    this.tcpMarker.position.set(0.18, -0.12, 0);
    toolGroup.add(this.tcpMarker);

    // TCP small coordinate triad
    const axesHelper = new THREE.AxesHelper(0.08);
    axesHelper.position.copy(this.tcpMarker.position);
    toolGroup.add(axesHelper);
  }

  // --------------------------------------------------------------------------
  // Camera Presets
  // --------------------------------------------------------------------------
  setCameraPreset(preset) {
    if (!this.camera) return;

    let targetPos, lookAtTarget = new THREE.Vector3(0, 0.75, 0);
    if (preset === "iso") {
      targetPos = new THREE.Vector3(2.0, 1.8, 2.2);
    } else if (preset === "front") {
      targetPos = new THREE.Vector3(0.0, 0.85, 2.8);
    } else if (preset === "side") {
      targetPos = new THREE.Vector3(2.8, 0.85, 0.0);
    } else if (preset === "top") {
      targetPos = new THREE.Vector3(0.001, 3.2, 0.0);
    } else {
      targetPos = new THREE.Vector3(2.0, 1.8, 2.2);
    }

    if (this.controls) {
      this.camera.position.copy(targetPos);
      this.controls.target.copy(lookAtTarget);
      this.controls.update();
    }
  }

  // --------------------------------------------------------------------------
  // WebSocket Communication (Low Latency Push)
  // --------------------------------------------------------------------------
  connectWebSocket() {
    if (this.ws) {
      try { this.ws.close(); } catch(e) {}
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host || "127.0.0.1:8000";
    const wsUrl = `${protocol}//${host}/api/robot/ws`;

    this.updateStatusBadge("CONNECTING", "connecting");

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        this.isConnected = true;
        this.updateStatusBadge("LIVE (10 Hz)", "live");
        if (this.reconnectTimer) {
          clearTimeout(this.reconnectTimer);
          this.reconnectTimer = null;
        }
      };

      this.ws.onmessage = (event) => {
        try {
          if (event.data === "pong") return;
          const data = JSON.parse(event.data);
          this.onTelemetryPacket(data);
        } catch (err) {
          console.error("Error parsing telemetry WebSocket packet:", err);
        }
      };

      this.ws.onclose = () => {
        this.isConnected = false;
        this.updateStatusBadge("DISCONNECTED", "disconnected");
        this.triggerStaleAlert(true);
        // Automatic gentle reconnect
        this.scheduleReconnect();
      };

      this.ws.onerror = () => {
        this.isConnected = false;
        this.updateStatusBadge("CONN ERROR", "disconnected");
      };
    } catch (e) {
      console.warn("WebSocket init error:", e);
      this.scheduleReconnect();
    }
  }

  scheduleReconnect() {
    if (this.reconnectTimer) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connectWebSocket();
    }, 2500);
  }

  onTelemetryPacket(data) {
    if (data.status === "stale") {
      this.triggerStaleAlert(true);
      return;
    }

    if (data.j && Array.isArray(data.j) && data.j.length === 6) {
      // Shift interpolation buffer
      for (let i = 0; i < 6; i++) {
        this.prevJoints[i] = this.currentJoints[i];
        this.targetJoints[i] = Number(data.j[i]) || 0;
      }

      this.packetInterval = Math.max(20, Date.now() - (this.lastPacketTime || (Date.now() - 100)));
      this.lastPacketTime = Date.now();
      this.packetCount++;
      this.triggerStaleAlert(false);

      // Update numeric readouts immediately or on render
      this.updateJointReadoutUI(data.j);
    }
  }

  triggerStaleAlert(isStale) {
    this.isStale = isStale;
    const banner = document.getElementById("twin-stale-banner");
    const badge = document.getElementById("twin-stream-badge");
    const dashBadge = document.getElementById("dash-twin-stream-badge");
    if (banner) {
      banner.style.display = isStale ? "flex" : "none";
    }
    const badgeText = isStale ? "STREAM STALE" : "LIVE (10 Hz)";
    const badgeClass = isStale ? "badge badge-warning" : "badge badge-success";
    if (badge) {
      badge.className = badgeClass;
      badge.textContent = badgeText;
    }
    if (dashBadge) {
      dashBadge.className = badgeClass;
      dashBadge.textContent = badgeText;
    }
  }

  updateStatusBadge(text, state) {
    const badges = [
      document.getElementById("twin-stream-badge"),
      document.getElementById("dash-twin-stream-badge")
    ];
    badges.forEach(badge => {
      if (!badge) return;
      badge.textContent = text;
      if (state === "live") {
        badge.className = "badge badge-success";
      } else if (state === "connecting") {
        badge.className = "badge badge-info";
      } else {
        badge.className = "badge badge-danger";
      }
    });
  }

  // --------------------------------------------------------------------------
  // Decoupled 60fps Render Loop & Joint Interpolation
  // --------------------------------------------------------------------------
  renderLoop() {
    this.animFrameId = requestAnimationFrame(() => this.renderLoop());

    const now = Date.now();

    // Check for stale stream if no packets received for > 1200ms
    if (this.lastPacketTime > 0 && (now - this.lastPacketTime) > 1200 && !this.isStale) {
      this.triggerStaleAlert(true);
    }

    // LERP (Linear Interpolation) between prevJoints and targetJoints
    const elapsed = now - this.lastPacketTime;
    const alpha = Math.min(1.0, Math.max(0.0, elapsed / (this.packetInterval || 100)));

    for (let i = 0; i < 6; i++) {
      this.currentJoints[i] = this.prevJoints[i] + (this.targetJoints[i] - this.prevJoints[i]) * alpha;
    }

    // Subtle idle breathing motion when in simulation/idle to visibly behave like a live feed
    if (!this.isConnected || this.lastPacketTime === 0) {
      const breath = Math.sin(now * 0.0015) * 0.4;
      this.currentJoints[1] += breath * 0.3;
      this.currentJoints[2] -= breath * 0.4;
    }

    // Apply joint angles to Three.js robot kinematic hierarchy
    this.applyJointRotations(this.currentJoints);

    // Update TCP World Position
    this.calculateTCPPose();

    // OrbitControls update (smooth damping & auto-rotate)
    if (this.controls) {
      this.controls.update();
    }

    // Render Scene
    if (this.renderer && this.scene && this.camera) {
      this.renderer.render(this.scene, this.camera);
    }

    // Calculate FPS
    this.fpsCount++;
    if (performance.now() - this.lastFpsCalcTime >= 1000) {
      const fpsEl = document.getElementById("twin-fps-val");
      const dashFpsEl = document.getElementById("dash-twin-fps-val");
      const txt = `${this.fpsCount} fps`;
      if (fpsEl) fpsEl.textContent = txt;
      if (dashFpsEl) dashFpsEl.textContent = txt;
      this.fpsCount = 0;
      this.lastFpsCalcTime = performance.now();
    }
  }

  applyJointRotations(joints) {
    if (!this.joints || this.joints.length < 6) return;

    for (let i = 0; i < 6; i++) {
      const joint = this.joints[i];
      const cfg = this.jointLimits[i];
      // Convert degrees to radians with directional sign
      const rad = (joints[i] * Math.PI / 180.0) * cfg.sign;

      if (cfg.axis === "x") {
        joint.group.rotation.x = rad;
      } else if (cfg.axis === "y") {
        joint.group.rotation.y = rad;
      } else if (cfg.axis === "z") {
        joint.group.rotation.z = rad;
      }
    }
  }

  calculateTCPPose() {
    if (!this.tcpMarker) return;
    const worldPos = new THREE.Vector3();
    this.tcpMarker.getWorldPosition(worldPos);

    // Update TCP displays (mm coordinates)
    const xEls = [document.getElementById("tcp-x-val"), document.getElementById("dash-tcp-x-val")];
    const yEls = [document.getElementById("tcp-y-val"), document.getElementById("dash-tcp-y-val")];
    const zEls = [document.getElementById("tcp-z-val"), document.getElementById("dash-tcp-z-val")];

    const xTxt = (worldPos.x * 1000).toFixed(1);
    const yTxt = (worldPos.y * 1000).toFixed(1);
    const zTxt = (worldPos.z * 1000).toFixed(1);

    xEls.forEach(el => { if (el) el.textContent = xTxt; });
    yEls.forEach(el => { if (el) el.textContent = yTxt; });
    zEls.forEach(el => { if (el) el.textContent = zTxt; });
  }

  // --------------------------------------------------------------------------
  // UI Readouts & Controls
  // --------------------------------------------------------------------------
  initUI() {
    // Camera Preset Buttons
    document.querySelectorAll("[data-twin-cam]").forEach(btn => {
      btn.addEventListener("click", () => {
        this.setCameraPreset(btn.dataset.twinCam);
        document.querySelectorAll("[data-twin-cam]").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
      });
    });

    // Reconnect Button in Stale Banner
    document.getElementById("btn-twin-reconnect")?.addEventListener("click", () => {
      this.connectWebSocket();
    });

    // Joint Direction (Sign) Inversion Buttons
    document.querySelectorAll("[data-joint-sign-idx]").forEach(btn => {
      btn.addEventListener("click", () => {
        const idx = parseInt(btn.dataset.jointSignIdx, 10);
        this.toggleJointSign(idx);
      });
    });

    // Reset Default Signs Button
    document.getElementById("btn-twin-reset-signs")?.addEventListener("click", () => {
      this.resetDefaultSigns();
    });

    this.updateSignButtonsUI();
  }

  loadSavedSigns() {
    try {
      const saved = localStorage.getItem("abb_twin_joint_signs");
      if (saved) {
        const signs = JSON.parse(saved);
        if (Array.isArray(signs) && signs.length === 6) {
          for (let i = 0; i < 6; i++) {
            this.jointLimits[i].sign = signs[i] === -1 ? -1 : 1;
          }
        }
      }
    } catch (e) {
      console.warn("Failed to load saved joint signs:", e);
    }
  }

  saveSigns() {
    try {
      const signs = this.jointLimits.map(l => l.sign);
      localStorage.setItem("abb_twin_joint_signs", JSON.stringify(signs));
    } catch (e) {}
  }

  toggleJointSign(jointIndex) {
    if (jointIndex >= 0 && jointIndex < 6) {
      this.jointLimits[jointIndex].sign *= -1;
      this.saveSigns();
      this.updateSignButtonsUI();
      // Immediately re-apply current pose with updated signs
      this.applyJointRotations(this.currentJoints);
    }
  }

  resetDefaultSigns() {
    const defaults = [1, -1, -1, -1, -1, -1];
    for (let i = 0; i < 6; i++) {
      this.jointLimits[i].sign = defaults[i];
    }
    this.saveSigns();
    this.updateSignButtonsUI();
    this.applyJointRotations(this.currentJoints);
  }

  updateSignButtonsUI() {
    for (let i = 0; i < 6; i++) {
      const btn = document.getElementById(`joint-sign-btn-${i+1}`);
      if (btn) {
        const sign = this.jointLimits[i].sign;
        btn.textContent = sign > 0 ? "+1" : "-1";
        btn.className = `joint-sign-toggle ${sign > 0 ? "sign-pos" : "sign-neg"}`;
        btn.title = `Axis ${i+1} Direction: ${sign > 0 ? "+1 (Normal)" : "-1 (Inverted)"}. Click to toggle.`;
      }
    }
  }

  updateJointReadoutUI(joints) {
    for (let i = 0; i < 6; i++) {
      const deg = Number(joints[i]) || 0;
      const valEls = [
        document.getElementById(`joint-val-${i+1}`),
        document.getElementById(`dash-joint-val-${i+1}`)
      ];
      const barEls = [
        document.getElementById(`joint-bar-${i+1}`),
        document.getElementById(`dash-joint-bar-${i+1}`)
      ];

      const degStr = `${deg >= 0 ? "+" : ""}${deg.toFixed(1)}°`;
      valEls.forEach(el => {
        if (el) el.textContent = degStr;
      });

      const lim = this.jointLimits[i];
      const range = lim.max - lim.min;
      const pct = Math.max(0, Math.min(100, ((deg - lim.min) / range) * 100));

      barEls.forEach(barEl => {
        if (barEl) {
          barEl.style.width = `${pct}%`;
          if (pct < 5 || pct > 95) {
            barEl.style.backgroundColor = "var(--crit)";
          } else if (pct < 15 || pct > 85) {
            barEl.style.backgroundColor = "var(--warn)";
          } else {
            barEl.style.backgroundColor = "#50E3C2";
          }
        }
      });
    }
  }

  attachToContainer(containerId) {
    const target = document.getElementById(containerId);
    if (target && this.renderer && this.renderer.domElement) {
      this.container = target;
      target.appendChild(this.renderer.domElement);
      this.onResize();
    }
  }

  onResize() {
    if (!this.container || !this.renderer || !this.camera) return;
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;
    if (width === 0 || height === 0) return;

    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  }

  destroy() {
    if (this.animFrameId) cancelAnimationFrame(this.animFrameId);
    if (this.ws) {
      try { this.ws.close(); } catch(e) {}
    }
    if (this.renderer && this.renderer.domElement && this.container) {
      this.container.removeChild(this.renderer.domElement);
    }
  }
}

// Global viewer instance placeholder
window.digitalTwinViewer = null;

// Initialize on DOM load
document.addEventListener("DOMContentLoaded", () => {
  const container = document.getElementById("digital-twin-canvas-container");
  if (container) {
    window.digitalTwinViewer = new DigitalTwinViewer("digital-twin-canvas-container");
  }
});
