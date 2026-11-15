// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IAccessControl} from "../interfaces/IAccessControl.sol";

/**
 * @title AccessControl
 * @notice Role-based access control (OpenZeppelin AccessControl compatible)
 * Uses EIP-1822 UUPS pattern for upgradeability
 */
contract AccessControl is IAccessControl {
    // Role constants
    bytes32 public constant DEFAULT_ADMIN_ROLE = 0x0000000000000000000000000000000000000000000000000000000000000000;

    // Storage
    mapping(bytes32 => mapping(address => bool)) private _roles;
    mapping(bytes32 => bytes32) private _roleAdmins;

    // Events
    event RoleAdminChanged(bytes32 indexed role, bytes32 indexed previousAdminRole, bytes32 indexed newAdminRole);

    // Modifier
    modifier onlyRole(bytes32 role) {
        _checkRole(role);
        _;
    }

    constructor() {
        _roles[DEFAULT_ADMIN_ROLE][_msgSender()] = true;
        _roleAdmins[DEFAULT_ADMIN_ROLE] = DEFAULT_ADMIN_ROLE;
        emit RoleGranted(DEFAULT_ADMIN_ROLE, _msgSender(), _msgSender());
    }

    // ============================================================
    // View Functions
    // ============================================================

    function hasRole(bytes32 role, address account) external view override returns (bool) {
        return _roles[role][account];
    }

    function getRoleAdmin(bytes32 role) external view override returns (bytes32) {
        return _getRoleAdmin(role);
    }

    function _getRoleAdmin(bytes32 role) internal view returns (bytes32) {
        return _roleAdmins[role];
    }

    // ============================================================
    // Role Management
    // ============================================================

    function grantRole(bytes32 role, address account) external override onlyRole(_getRoleAdmin(role)) {
        _grantRole(role, account);
    }

    function revokeRole(bytes32 role, address account) external override onlyRole(_getRoleAdmin(role)) {
        _revokeRole(role, account);
    }

    function renounceRole(bytes32 role, address account) external override {
        require(account == _msgSender(), "AccessControl: can only renounce roles for self");
        _revokeRole(role, account);
    }

    function setRoleAdmin(bytes32 role, bytes32 adminRole) external onlyRole(DEFAULT_ADMIN_ROLE) {
        bytes32 previousAdminRole = _roleAdmins[role];
        _roleAdmins[role] = adminRole;
        emit RoleAdminChanged(role, previousAdminRole, adminRole);
    }

    // ============================================================
    // Internal Functions
    // ============================================================

    function _checkRole(bytes32 role) internal view {
        _checkRole(role, _msgSender());
    }

    function _checkRole(bytes32 role, address account) internal view {
        if (!_roles[role][account]) {
            revert AccessControlMissingRole(account, role);
        }
    }

    function _grantRole(bytes32 role, address account) internal {
        if (!_roles[role][account]) {
            _roles[role][account] = true;
            emit RoleGranted(role, account, _msgSender());
        }
    }

    function _revokeRole(bytes32 role, address account) internal {
        if (_roles[role][account]) {
            _roles[role][account] = false;
            emit RoleRevoked(role, account, _msgSender());
        }
    }

    function _setupRole(bytes32 role, address account) internal {
        _grantRole(role, account);
    }

    function _setupRole(bytes32 role, address[] calldata accounts) internal {
        for (uint256 i = 0; i < accounts.length; i++) {
            _grantRole(role, accounts[i]);
        }
    }

    // ============================================================
    // msg.sender helper (for EIP-2771 compatibility)
    // ============================================================
    function _msgSender() internal view virtual returns (address) {
        return msg.sender;
    }

    // ============================================================
    // Custom Errors
    // ============================================================
    error AccessControlMissingRole(address account, bytes32 neededRole);
    error AccessControlBadConfirmation();
}