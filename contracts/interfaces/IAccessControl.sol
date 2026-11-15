// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title IAccessControl
 * @notice Role-based access control interface (OpenZeppelin AccessControl compatible)
 */
interface IAccessControl {
    // Events
    event RoleGranted(bytes32 indexed role, address indexed account, address indexed sender);
    event RoleRevoked(bytes32 indexed role, address indexed account, address indexed sender);

    // Role management
    function hasRole(bytes32 role, address account) external view returns (bool);
    function getRoleAdmin(bytes32 role) external view returns (bytes32);
    function grantRole(bytes32 role, address account) external;
    function revokeRole(bytes32 role, address account) external;
    function renounceRole(bytes32 role, address account) external;

    // Role constants
    function DEFAULT_ADMIN_ROLE() external view returns (bytes32);
}