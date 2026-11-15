// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IProxyAdmin} from "../interfaces/IUpgradeable.sol";
import {IUUPSUpgradeable} from "../interfaces/IUpgradeable.sol";
import {ERC1967Proxy} from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";
import {ERC1967Utils} from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Utils.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title ProxyAdmin
 * @notice Admin contract for managing UUPS proxies
 * @dev Owned by multisig, manages proxy upgrades and admin changes
 */
contract ProxyAdmin is Ownable, IProxyAdmin {
    // Events
    event ProxyRegistered(string name, address indexed proxy);
    event ProxyUnregistered(string name);

    // Storage
    mapping(string => address) private _proxies;

    constructor(address initialOwner) Ownable(initialOwner) {}

    // ============================================================
    // Proxy Management
    // ============================================================

    /**
     * @notice Register a proxy for management
     * @param name Human-readable name for the proxy
     * @param proxy Address of the proxy contract
     */
    function registerProxy(string calldata name, address proxy) external onlyOwner {
        require(proxy != address(0), "ProxyAdmin: zero proxy address");
        require(_proxies[name] == address(0), "ProxyAdmin: proxy name already registered");
        _proxies[name] = proxy;
        emit ProxyRegistered(name, proxy);
    }

    /**
     * @notice Unregister a proxy
     * @param name Name of the proxy to unregister
     */
    function unregisterProxy(string calldata name) external onlyOwner {
        require(_proxies[name] != address(0), "ProxyAdmin: proxy not registered");
        delete _proxies[name];
        emit ProxyUnregistered(name);
    }

    /**
     * @notice Upgrade a registered proxy
     * @param proxy Proxy address
     * @param implementation New implementation address
     */
    function upgrade(address proxy, address implementation) external override onlyOwner {
        require(proxy != address(0), "ProxyAdmin: zero proxy address");
        require(implementation != address(0), "ProxyAdmin: zero implementation address");

        IUUPSUpgradeable(proxy).upgradeTo(implementation);
        emit ProxyUpgraded(proxy, implementation);
    }

    /**
     * @notice Upgrade a registered proxy and call initialization
     * @param proxy Proxy address
     * @param implementation New implementation address
     * @param data Calldata for initialization
     */
    function upgradeAndCall(
        address proxy,
        address implementation,
        bytes calldata data
    ) external override onlyOwner {
        require(proxy != address(0), "ProxyAdmin: zero proxy address");
        require(implementation != address(0), "ProxyAdmin: zero implementation address");

        IUUPSUpgradeable(proxy).upgradeToAndCall(implementation, data);
        emit ProxyUpgraded(proxy, implementation);
    }

    /**
     * @notice Change proxy admin (for transparent proxies)
     * @param proxy Proxy address
     * @param newAdmin New admin address
     */
    function changeAdmin(address proxy, address newAdmin) external override onlyOwner {
        require(proxy != address(0), "ProxyAdmin: zero proxy address");
        require(newAdmin != address(0), "ProxyAdmin: zero new admin address");

        // Use low-level call to change admin on transparent proxy
        bytes memory data = abi.encodeWithSelector(bytes4(keccak256("changeAdmin(address)")), newAdmin);
        (bool success, ) = proxy.call(data);
        require(success, "ProxyAdmin: changeAdmin failed");
        emit ProxyAdminChanged(address(this), newAdmin);
    }

    // ============================================================
    // View Functions
    // ============================================================

    function getAdmin(address proxy) external view override returns (address) {
        // ERC1967 admin slot
        bytes32 slot = 0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103;
        bytes32 adminBytes;
        assembly {
            adminBytes := sload(slot)
            // Mask to extract 20-byte address from 32-byte slot and return directly
            adminBytes := and(adminBytes, 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF)
        }
        assembly {
            return(adminBytes, 0x20)
        }
    }

    function getImplementation(address proxy) external view override returns (address) {
        // ERC1967 implementation slot
        bytes32 slot = 0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc;
        bytes32 implBytes;
        assembly {
            implBytes := sload(slot)
            // Mask to extract 20-byte address from 32-byte slot and return directly
            implBytes := and(implBytes, 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF)
        }
        assembly {
            return(implBytes, 0x20)
        }
    }

    function getProxy(string calldata name) external view returns (address) {
        return _proxies[name];
    }

    function listProxies() external view returns (string[] memory names, address[] memory proxies) {
        // This is a simplified version - in production you'd use an EnumerableMap
        // For now, return empty arrays as this is mainly for off-chain querying
        return (new string[](0), new address[](0));
    }
}