// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IUUPSUpgradeable} from "../interfaces/IUpgradeable.sol";
import {ERC1967Proxy} from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";
import {ERC1967Utils} from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Utils.sol";
import {IERC1822Proxiable} from "@openzeppelin/contracts/interfaces/draft-IERC1822.sol";

/**
 * @title UUPSProxy
 * @notice UUPS (Universal Upgradeable Proxy Standard) implementation
 * @dev Uses OpenZeppelin's ERC1967Proxy as base, adds authorization checks
 */
contract UUPSProxy is ERC1967Proxy, IUUPSUpgradeable {
    function _msgSender() internal view virtual returns (address) {
        return msg.sender;
    }

    constructor(address implementation_, bytes memory data) ERC1967Proxy(implementation_, data) {
        require(
            IERC1822Proxiable(implementation_).proxiableUUID() == ERC1967Utils.IMPLEMENTATION_SLOT,
            "UUPSProxy: implementation not UUPS compliant"
        );
    }

    /**
     * @notice Upgrade the implementation
     * @param newImplementation Address of new implementation
     * @dev Only callable by address with UPGRADER_ROLE on implementation
     */
    function upgradeTo(address newImplementation) external override {
        _authorizeUpgrade(newImplementation);
        ERC1967Utils.upgradeToAndCall(newImplementation, "");
        emit Upgraded(newImplementation);
    }

    /**
     * @notice Upgrade and call initialization function
     * @param newImplementation Address of new implementation
     * @param data Calldata for initialization
     */
    function upgradeToAndCall(address newImplementation, bytes calldata data) external override {
        _authorizeUpgrade(newImplementation);
        ERC1967Utils.upgradeToAndCall(newImplementation, data);
        emit Upgraded(newImplementation);
    }

    /**
     * @notice Get current implementation address
     */
    function implementation() external view override returns (address) {
        return ERC1967Utils.getImplementation();
    }

    /**
     * @notice Authorize upgrade - implemented by logic contract
     * @dev Called via delegatecall from _authorizeUpgrade
     */
    function authorizeUpgrade(address newImplementation) external override {
        // This will be overridden by the implementation contract
        // The actual logic lives in IDRCToken._authorizeUpgrade
    }

    /**
     * @notice Internal authorize upgrade - calls implementation's authorizeUpgrade
     */
    function _authorizeUpgrade(address newImplementation) internal {
        // Delegate call to implementation's authorizeUpgrade
        (bool success, ) = newImplementation.delegatecall(
            abi.encodeWithSelector(IUUPSUpgradeable.authorizeUpgrade.selector, newImplementation)
        );
        if (!success) {
            revert("UUPSProxy: upgrade not authorized");
        }
        emit UpgradeAuthorized(newImplementation, msg.sender);
    }
}