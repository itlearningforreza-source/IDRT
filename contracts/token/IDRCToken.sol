// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "../interfaces/IERC20.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {UUPSUpgradeable} from "@openzeppelin/contracts/proxy/utils/UUPSUpgradeable.sol";
import {Context} from "@openzeppelin/contracts/utils/Context.sol";
import {Initializable} from "@openzeppelin/contracts/proxy/utils/Initializable.sol";

/**
 * @title IDRCToken
 * @notice IDR Coin (IDRC) - Fiat-collateralized stablecoin pegged 1:1 to Indonesian Rupiah
 * @dev Implements ERC-20, EIP-2612 Permit, AccessControl, Pausable, Blacklist, UUPS Upgradeability
 * Uses OpenZeppelin v5 contracts for battle-tested components
 * 
 * NOTE: For UUPS proxy compatibility, name and symbol are stored in custom state variables
 * and initialized via the initialize() function, not the ERC20 constructor.
 * Does NOT inherit from ERC20/ERC20Permit to avoid proxy initialization issues.
 */
contract IDRCToken is
    Initializable,
    AccessControl,
    Pausable,
    ReentrancyGuard,
    UUPSUpgradeable,
    IERC20
{
    function _msgSender() internal view override(Context) returns (address) {
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
    mapping(address => uint256) private _balances;
    mapping(address => mapping(address => uint256)) private _allowances;
    uint256 private _totalSupply;
    
    // Custom name/symbol storage for proxy compatibility
    string private _name;
    string private _symbol;
    
    mapping(address => bool) public isBlacklisted;
    uint256 public supplyCap;
    bytes32 public reserveProofHash;
    
    // EIP-2612 Permit state
    mapping(address => uint256) private _nonces;
    bytes32 private _domainSeparator;
    bytes32 public constant PERMIT_TYPEHASH = keccak256("Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)");

    // Events (Transfer and Approval are defined in IERC20 interface)
    event Minted(address indexed to, uint256 amount);
    event Burned(address indexed from, uint256 amount);
    event Blacklisted(address indexed account);
    event Unblacklisted(address indexed account);
    event SupplyCapUpdated(uint256 newCap);
    event ReserveProofUpdated(bytes32 proofHash);

    // Custom Errors (matching OpenZeppelin's IERC6093 standard errors)
    error ERC20InsufficientBalance(address sender, uint256 balance, uint256 needed);
    error ERC20InsufficientAllowance(address spender, uint256 allowance, uint256 needed);
    error ERC20InvalidSender(address sender);
    error ERC20InvalidReceiver(address receiver);
    error ERC20InvalidSpender(address spender);
    error ZeroAddress();
    error ZeroAmount();
    error SupplyCapExceeded(uint256 requested, uint256 cap);
    error BlacklistedAccount(address account);
    error NotBlacklisted(address account);
    error AlreadyBlacklisted(address account);

    // ============================================================
    // Constructor
    // ============================================================
    // Minimal constructor - does NOT initialize name/symbol/roles
    // All state initialization happens in initialize() for proxy compatibility
    constructor() {
        // Empty - all initialization in initialize()
    }

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
    ) public virtual initializer {
        // Set name and symbol (stored in custom variables for proxy)
        _name = name_;
        _symbol = symbol_;

        // EIP-2612 Permit initialization - build domain separator
        {
            uint256 chainId;
            assembly {
                chainId := chainid()
            }
            _domainSeparator = keccak256(
                abi.encode(
                    keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                    keccak256(bytes(name_)),
                    keccak256(bytes("1")),
                    chainId,
                    address(this)
                )
            );
        }

        // AccessControl initialization - set DEFAULT_ADMIN_ROLE
        _grantRole(DEFAULT_ADMIN_ROLE, admin);

        // Grant roles
        _grantRole(MINTER_ROLE, minter);
        _grantRole(PAUSER_ROLE, pauser);
        _grantRole(UPGRADER_ROLE, upgrader);
        _grantRole(BURNER_ROLE, burner);
        _grantRole(BLACKLISTER_ROLE, blacklister);

        // Supply cap
        supplyCap = supplyCap_ > 0 ? supplyCap_ : 10_000_000_000 * 10**18; // Default 10B IDRC

        // Reserve proof hash (empty initially)
        reserveProofHash = bytes32(0);
    }

    // ============================================================
    // ERC-20 View Functions
    // ============================================================
    function name() public view returns (string memory) {
        return _name;
    }

    function symbol() public view returns (string memory) {
        return _symbol;
    }

    function decimals() public pure returns (uint8) {
        return 18;
    }

    function totalSupply() public view returns (uint256) {
        return _totalSupply;
    }

    function balanceOf(address account) public view returns (uint256) {
        return _balances[account];
    }

    function allowance(address owner, address spender) public view returns (uint256) {
        return _allowances[owner][spender];
    }

    // EIP-2612 Permit view functions
    function nonces(address owner) public view returns (uint256) {
        return _nonces[owner];
    }

    function DOMAIN_SEPARATOR() public view returns (bytes32) {
        return _domainSeparator;
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
        if (_totalSupply + amount > supplyCap) revert SupplyCapExceeded(_totalSupply + amount, supplyCap);
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
        if (newCap < _totalSupply) revert SupplyCapExceeded(_totalSupply, newCap);
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
    // ERC-20 Transfer Functions
    // ============================================================
    function transfer(address to, uint256 amount) external whenNotPaused nonReentrant returns (bool) {
        _transfer(msg.sender, to, amount);
        return true;
    }

    function approve(address spender, uint256 amount) external whenNotPaused returns (bool) {
        _approve(msg.sender, spender, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external whenNotPaused nonReentrant returns (bool) {
        uint256 currentAllowance = _allowances[from][msg.sender];
        if (currentAllowance != type(uint256).max) {
            if (currentAllowance < amount) revert ERC20InsufficientAllowance(msg.sender, currentAllowance, amount);
            _approve(from, msg.sender, currentAllowance - amount);
        }
        _transfer(from, to, amount);
        return true;
    }

    function increaseAllowance(address spender, uint256 addedValue) external whenNotPaused returns (bool) {
        _approve(msg.sender, spender, _allowances[msg.sender][spender] + addedValue);
        return true;
    }

    function decreaseAllowance(address spender, uint256 subtractedValue) external whenNotPaused returns (bool) {
        uint256 currentAllowance = _allowances[msg.sender][spender];
        if (currentAllowance < subtractedValue) revert ERC20InsufficientAllowance(msg.sender, currentAllowance, subtractedValue);
        _approve(msg.sender, spender, currentAllowance - subtractedValue);
        return true;
    }

    // ============================================================
    // EIP-2612 Permit (with low-s enforcement)
    // ============================================================
    function permit(
        address owner,
        address spender,
        uint256 value,
        uint256 deadline,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) external {
        // Low-s enforcement per EIP-2612
        // secp256k1 curve order / 2 = 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0
        if (s > 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0) revert("ERC20Permit: invalid signature (high s)");

        // Standard EIP-2612 permit implementation
        bytes32 structHash = keccak256(
            abi.encode(PERMIT_TYPEHASH, owner, spender, value, _nonces[owner]++, deadline)
        );
        // EIP-191 prefix: "" = 0x1901
        bytes32 hash = keccak256(abi.encodePacked(hex"1901", _domainSeparator, structHash));
        address signer = ecrecover(hash, v, r, s);
        if (signer != owner) revert("ERC20Permit: invalid signature");
        if (block.timestamp > deadline) revert("ERC20Permit: expired deadline");
        _approve(owner, spender, value);
    }

    // ============================================================
    // Internal ERC-20 Functions
    // ============================================================
    function _transfer(address from, address to, uint256 amount) internal {
        if (from == address(0)) revert ERC20InvalidSender(from);
        if (to == address(0)) revert ERC20InvalidReceiver(to);
        
        // Blacklist checks
        if (isBlacklisted[from]) revert BlacklistedAccount(from);
        if (isBlacklisted[to]) revert BlacklistedAccount(to);

        uint256 fromBalance = _balances[from];
        if (fromBalance < amount) revert ERC20InsufficientBalance(from, fromBalance, amount);

        _balances[from] = fromBalance - amount;
        _balances[to] += amount;
        emit Transfer(from, to, amount);
    }

    function _mint(address account, uint256 amount) internal {
        if (account == address(0)) revert ERC20InvalidReceiver(account);
        _totalSupply += amount;
        _balances[account] += amount;
        emit Transfer(address(0), account, amount);
    }

    function _burn(address account, uint256 amount) internal {
        if (account == address(0)) revert ERC20InvalidSender(account);
        uint256 accountBalance = _balances[account];
        if (accountBalance < amount) revert ERC20InsufficientBalance(account, accountBalance, amount);
        _balances[account] = accountBalance - amount;
        _totalSupply -= amount;
        emit Transfer(account, address(0), amount);
    }

    function _approve(address owner, address spender, uint256 amount) internal {
        if (owner == address(0)) revert ERC20InvalidSender(owner);
        if (spender == address(0)) revert ERC20InvalidSpender(spender);
        _allowances[owner][spender] = amount;
        emit Approval(owner, spender, amount);
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
