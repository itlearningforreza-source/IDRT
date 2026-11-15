// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title IUUPSUpgradeable
 * @notice UUPS upgradeable interface (EIP-1822 compatible)
 */
interface IUUPSUpgradeable {
    event Upgraded(address indexed implementation);
    event UpgradeAuthorized(address indexed implementation, address indexed authorizer);

    function upgradeTo(address newImplementation) external;
    function upgradeToAndCall(address newImplementation, bytes calldata data) external;
    function implementation() external view returns (address);
    function authorizeUpgrade(address newImplementation) external;
}

/**
 * @title IProxyAdmin
 * @notice Proxy admin interface for managing UUPS proxies
 */
interface IProxyAdmin {
    event ProxyAdminChanged(address indexed previousAdmin, address indexed newAdmin);
    event ProxyUpgraded(address indexed proxy, address indexed implementation);

    function upgrade(address proxy, address implementation) external;
    function upgradeAndCall(address proxy, address implementation, bytes calldata data) external;
    function changeAdmin(address proxy, address newAdmin) external;
    function getAdmin(address proxy) external view returns (address);
    function getImplementation(address proxy) external view returns (address);
}

/**
 * @title IIDRCUpgradeable
 * @notice IDRC-specific upgradeable interface for versioned migrations
 */
interface IIDRCUpgradeable {
    event VersionUpdated(uint256 indexed version, string name);
    event MigrationCompleted(uint256 indexed fromVersion, uint256 indexed toVersion);

    function VERSION() external view returns (uint256);
    function initializeV2(address admin, address minter, address pauser, address upgrader, address burner, address blacklister) external;
    function initializeV3(address admin, address minter, address pauser, address upgrader, address burner, address blacklister, uint256 supplyCap) external;
    function migrateFromV1() external;
    function migrateFromV2() external;
}