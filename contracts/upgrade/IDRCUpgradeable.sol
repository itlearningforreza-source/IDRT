// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IIDRCUpgradeable} from "../interfaces/IUpgradeable.sol";
import {IDRCToken} from "../token/IDRCToken.sol";
import {Context} from "@openzeppelin/contracts/utils/Context.sol";

/**
 * @title IDRCUpgradeable
 * @notice Versioned upgrade logic for IDRC token
 * @dev Handles migrations between contract versions
 */
contract IDRCUpgradeable is IDRCToken, IIDRCUpgradeable {
    // _msgSender is inherited from IDRCToken (which overrides Context)
    
    // ============================================================
    // Version Constants
    // ============================================================
    uint256 public constant VERSION_V1 = 1;
    uint256 public constant VERSION_V2 = 2;
    uint256 public constant VERSION_V3 = 3;
    uint256 public override VERSION = VERSION_V3; // Current version

    // ============================================================
    // State Variables
    // ============================================================
    uint256 private _initializedVersion;

    // Events (defined in interface)

    // Custom Errors
    error InvalidVersion(uint256 version);
    error AlreadyInitialized(uint256 version);
    error MigrationNotAllowed(uint256 fromVersion);

    // ============================================================
    // Constructor
    // ============================================================
    // Minimal constructor - all initialization in initialize()
    constructor() {}

    // ============================================================
    // Initializer (for UUPS Proxy)
    // ============================================================
    // Note: No initializer modifier here - parent IDRCToken.initialize has it
    function initialize(
        string memory name_,
        string memory symbol_,
        address admin,
        address minter,
        address pauser,
        address upgrader,
        address burner,
        address blacklister,
        uint256 supplyCap_
    ) public virtual override {
        // Call parent initialize (which has the initializer modifier)
        super.initialize(name_, symbol_, admin, minter, pauser, upgrader, burner, blacklister, supplyCap_);
        
        _initializedVersion = VERSION_V3;
    }

    // ============================================================
    // Migration Functions
    // ============================================================

    /**
     * @notice Migrate from V1 to current version
     * @dev Called after upgrade to V2/V3
     */
    function migrateFromV1() external onlyRole(UPGRADER_ROLE) {
        require(_initializedVersion == VERSION_V1, "MigrationNotAllowed");
        // V1 to V2: supply cap was already set in initialize, no extra migration needed
        _initializedVersion = VERSION_V2;
        emit MigrationCompleted(VERSION_V1, VERSION_V2);
    }

    /**
     * @notice Migrate from V2 to current version
     * @dev Called after upgrade to V3
     */
    function migrateFromV2() external onlyRole(UPGRADER_ROLE) {
        require(_initializedVersion == VERSION_V2, "MigrationNotAllowed");
        // V2 to V3: no additional state changes needed
        _initializedVersion = VERSION_V3;
        emit MigrationCompleted(VERSION_V2, VERSION_V3);
    }

    // ============================================================
    // Upgrade Authorization (UUPS)
    // ============================================================
    // _authorizeUpgrade is inherited from IDRCToken

    // ============================================================
    // Initialize Functions (for proxy upgrades)
    // ============================================================
    function initializeV2(
        address admin,
        address minter,
        address pauser,
        address upgrader,
        address burner,
        address blacklister
    ) external override onlyRole(DEFAULT_ADMIN_ROLE) {
        require(_initializedVersion == VERSION_V1, "InvalidVersion");

        _setupRole(MINTER_ROLE, minter);
        _setupRole(PAUSER_ROLE, pauser);
        _setupRole(UPGRADER_ROLE, upgrader);
        _setupRole(BURNER_ROLE, burner);
        _setupRole(BLACKLISTER_ROLE, blacklister);

        _initializedVersion = VERSION_V2;
        emit MigrationCompleted(VERSION_V1, VERSION_V2);
    }

    function initializeV3(
        address admin,
        address minter,
        address pauser,
        address upgrader,
        address burner,
        address blacklister,
        uint256 supplyCap_
    ) external override onlyRole(DEFAULT_ADMIN_ROLE) {
        require(_initializedVersion == VERSION_V2, "InvalidVersion");

        _setupRole(MINTER_ROLE, minter);
        _setupRole(PAUSER_ROLE, pauser);
        _setupRole(UPGRADER_ROLE, upgrader);
        _setupRole(BURNER_ROLE, burner);
        _setupRole(BLACKLISTER_ROLE, blacklister);

        supplyCap = supplyCap_;

        _initializedVersion = VERSION_V3;
        emit MigrationCompleted(VERSION_V2, VERSION_V3);
    }

    // ============================================================
    // View Functions
    // ============================================================
    function getInitializedVersion() external view returns (uint256) {
        return _initializedVersion;
    }
}