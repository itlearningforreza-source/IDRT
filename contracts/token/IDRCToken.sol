// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "../interfaces/IERC20.sol";
import {AccessControl} from "../access/AccessControl.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {ERC20Permit} from "@openzeppelin/contracts/token/ERC20/extensions/ERC20Permit.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {UUPSUpgradeable} from "@openzeppelin/contracts/proxy/utils/UUPSUpgradeable.sol";
import {Address} from "@openzeppelin/contracts/utils/Address.sol";
import {Context} from "@openzeppelin/contracts/utils/Context.sol";

/**
 * @title IDRCToken
 * @notice IDR Coin (IDRC) - Fiat-collateralized stablecoin pegged 1:1 to Indonesian Rupiah
 * @dev Implements ERC-20, EIP-2612 Permit, AccessControl, Pausable, Blacklist, UUPS Upgradeability
 * Uses OpenZeppelin v5 contracts for battle-tested components
 */
contract IDRCToken is
    ERC20,
    AccessControl,
    ERC20Permit,
    Pausable,
    ReentrancyGuard,
    UUPSUpgradeable
{
    function _msgSender() internal view override(Context, AccessControl) returns (address) {
        return msg.sender;
    }
    // ============================================================
    // Role Constants (keccak256 hashes)
    // ============================================================
    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");
    bytes32 public constant BURNER_ROLE = keccak256("BURNER_ROLE");
    bytes32 public constant PAUSER_ROLE = keccak256("PAUSER_ROLE");
    bytes32 public constant UPGRADER_ROLE = keccak256("UPGRADER_ROLE");
    bytes32 public constant BLACKLISTER_ROLE = keccak256("BLACKLISTER_ROLE");

    // ============================================================
    // State Variables
    // ============================================================
    mapping(address => bool) public isBlacklisted;
    uint256 public supplyCap;
    bytes32 public reserveProofHash;

    // Events
    event Minted(address indexed to, uint256 amount);
    event Burned(address indexed from, uint256 amount);
    event Blacklisted(address indexed account);
    event Unblacklisted(address indexed account);
    event SupplyCapUpdated(uint256 newCap);
    event ReserveProofUpdated(bytes32 proofHash);

    // Custom Errors
    error ZeroAddress();
    error ZeroAmount();
    error SupplyCapExceeded(uint256 requested, uint256 cap);
    error BlacklistedAccount(address account);
    error NotBlacklisted(address account);
    error AlreadyBlacklisted(address account);

    // ============================================================
    // Initializer (for UUPS Proxy)
    // ============================================================
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
    ) external virtual {
        // ERC20 and ERC20Permit are already initialized via constructor
        // This function is for proxy initialization only
        // Re-initialize roles and state for proxy

        // AccessControl initialization - set DEFAULT_ADMIN_ROLE
        _setupRole(DEFAULT_ADMIN_ROLE, admin);

        // Grant roles
        _setupRole(MINTER_ROLE, minter);
        _setupRole(PAUSER_ROLE, pauser);
        _setupRole(UPGRADER_ROLE, upgrader);
        _setupRole(BURNER_ROLE, burner);
        _setupRole(BLACKLISTER_ROLE, blacklister);

        // Supply cap
        supplyCap = supplyCap_ > 0 ? supplyCap_ : 10_000_000_000 * 10**18; // Default 10B IDRC

        // Reserve proof hash (empty initially)
        reserveProofHash = bytes32(0);
    }

    // ============================================================
    // Constructor
    // ============================================================
    constructor(
        string memory name_,
        string memory symbol_,
        address admin,
        address minter,
        address pauser,
        address upgrader,
        address burner,
        address blacklister,
        uint256 supplyCap_
    ) ERC20(name_, symbol_) ERC20Permit(name_) {
        require(admin != address(0), "IDRC: zero admin address");
        require(minter != address(0), "IDRC: zero minter address");
        require(pauser != address(0), "IDRC: zero pauser address");
        require(upgrader != address(0), "IDRC: zero upgrader address");
        require(burner != address(0), "IDRC: zero burner address");
        require(blacklister != address(0), "IDRC: zero blacklister address");

        // AccessControl initialization - set DEFAULT_ADMIN_ROLE
        _setupRole(DEFAULT_ADMIN_ROLE, admin);

        // Grant roles
        _setupRole(MINTER_ROLE, minter);
        _setupRole(PAUSER_ROLE, pauser);
        _setupRole(UPGRADER_ROLE, upgrader);
        _setupRole(BURNER_ROLE, burner);
        _setupRole(BLACKLISTER_ROLE, blacklister);

        // Supply cap
        supplyCap = supplyCap_ > 0 ? supplyCap_ : 10_000_000_000 * 10**18; // Default 10B IDRC

        // Reserve proof hash (empty initially)
        reserveProofHash = bytes32(0);
    }

    // ============================================================
    // ERC-20 View Functions (overrides for naming)
    // ============================================================
    function name() public view override(ERC20) returns (string memory) {
        return super.name();
    }

    function symbol() public view override(ERC20) returns (string memory) {
        return super.symbol();
    }

    function decimals() public view override(ERC20) returns (uint8) {
        return 18;
    }

    // ============================================================
    // Minting & Burning
    // ============================================================

    /**
     * @notice Mint new IDRC tokens to an address
     * @dev Only MINTER_ROLE can call. Used when fiat is deposited.
     */
    function mint(address to, uint256 amount) external onlyRole(MINTER_ROLE) nonReentrant whenNotPaused {
        if (to == address(0)) revert ZeroAddress();
        if (amount == 0) revert ZeroAmount();
        if (totalSupply() + amount > supplyCap) revert SupplyCapExceeded(totalSupply() + amount, supplyCap);
        if (isBlacklisted[to]) revert BlacklistedAccount(to);

        _mint(to, amount);
        emit Minted(to, amount);
    }

    /**
     * @notice Burn IDRC tokens from an address (issuer burn)
     * @dev Only BURNER_ROLE can call. Used when fiat is redeemed.
     */
    function issuerBurn(address from, uint256 amount) external onlyRole(BURNER_ROLE) nonReentrant whenNotPaused {
        if (from == address(0)) revert ZeroAddress();
        if (amount == 0) revert ZeroAmount();
        if (isBlacklisted[from]) revert BlacklistedAccount(from);

        _burn(from, amount);
        emit Burned(from, amount);
    }

    /**
     * @notice Burn own IDRC tokens (user burn)
     * @dev Any holder can burn their own tokens for fiat redemption.
     */
    function burn(uint256 amount) external nonReentrant whenNotPaused {
        if (amount == 0) revert ZeroAmount();
        if (isBlacklisted[msg.sender]) revert BlacklistedAccount(msg.sender);

        _burn(msg.sender, amount);
        emit Burned(msg.sender, amount);
    }

    /**
     * @notice Update maximum supply cap
     * @dev Only DEFAULT_ADMIN_ROLE can call.
     */
    function setSupplyCap(uint256 newCap) external onlyRole(DEFAULT_ADMIN_ROLE) {
        if (newCap < totalSupply()) revert SupplyCapExceeded(totalSupply(), newCap);
        supplyCap = newCap;
        emit SupplyCapUpdated(newCap);
    }

    // ============================================================
    // Pausable Functions
    // ============================================================
    function pause() external onlyRole(PAUSER_ROLE) {
        _pause();
    }

    function unpause() external onlyRole(PAUSER_ROLE) {
        _unpause();
    }

    // ============================================================
    // Blacklist Functions
    // ============================================================
    function blacklist(address account) external onlyRole(BLACKLISTER_ROLE) {
        if (account == address(0)) revert ZeroAddress();
        if (isBlacklisted[account]) revert AlreadyBlacklisted(account);
        isBlacklisted[account] = true;
        emit Blacklisted(account);
    }

    function unblacklist(address account) external onlyRole(BLACKLISTER_ROLE) {
        if (!isBlacklisted[account]) revert NotBlacklisted(account);
        isBlacklisted[account] = false;
        emit Unblacklisted(account);
    }

    // ============================================================
    // Reserve Proof Functions
    // ============================================================
    function updateReserveProof(bytes32 newHash) external onlyRole(DEFAULT_ADMIN_ROLE) {
        reserveProofHash = newHash;
        emit ReserveProofUpdated(newHash);
    }

    // ============================================================
    // ERC-20 Transfer Overrides (with blacklist + pause checks)
    // ============================================================
    function _update(address from, address to, uint256 value) internal override(ERC20) {
        // Blacklist checks
        if (from != address(0) && isBlacklisted[from]) revert BlacklistedAccount(from);
        if (to != address(0) && isBlacklisted[to]) revert BlacklistedAccount(to);

        // Pause check (whenNotPaused modifier on public functions, but internal _update needs explicit check)
        if (paused() && from != address(0) && to != address(0)) {
            revert EnforcedPause();
        }

        return super._update(from, to, value);
    }

    // ============================================================
    // UUPS Upgradeability
    // ============================================================
    function _authorizeUpgrade(address newImplementation) internal override onlyRole(UPGRADER_ROLE) {
        // Additional check: ensure new implementation is a valid contract
        require(newImplementation != address(0), "IDRC: zero address implementation");
        require(newImplementation.code.length > 0, "IDRC: new implementation is not a contract");
    }
}