// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title IDRCToken
 * @notice Simplified Production Reference Smart Contract for IDR Coin (IDRC).
 * IDRC is pegged 1:1 to the Indonesian Rupiah (IDR).
 * Includes AccessControl, Pausable, Blacklist, and EIP-2612 Permit standard interfaces.
 */
contract IDRCToken {
    // --- ERC-20 State ---
    string public name = "IDR Coin";
    string public symbol = "IDRC";
    uint8 public constant decimals = 18;
    uint256 public totalSupply;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    // --- Access Control Roles ---
    bytes32 public constant DEFAULT_ADMIN_ROLE = 0x00;
    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");
    bytes32 public constant PAUSER_ROLE = keccak256("PAUSER_ROLE");
    bytes32 public constant BLACKLISTER_ROLE = keccak256("BLACKLISTER_ROLE");

    mapping(bytes32 => mapping(address => bool)) private _roles;

    // --- Pausable & Blacklist State ---
    bool public paused;
    mapping(address => bool) public isBlacklisted;

    // --- EIP-2612 Permit State ---
    mapping(address => uint256) public nonces;
    bytes32 public DOMAIN_SEPARATOR;
    bytes32 public constant PERMIT_TYPEHASH =
        keccak256("Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)");

    // --- Events ---
    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
    event RoleGranted(bytes32 indexed role, address indexed account, address indexed sender);
    event RoleRevoked(bytes32 indexed role, address indexed account, address indexed sender);
    event Paused(address account);
    event Unpaused(address account);
    event Blacklisted(address indexed account);
    event Unblacklisted(address indexed account);

    // --- Modifiers ---
    modifier onlyRole(bytes32 role) {
        require(_roles[role][msg.sender], "IDRC: caller missing required role");
        _;
    }

    modifier whenNotPaused() {
        require(!paused, "IDRC: token transfers are paused");
        _;
    }

    modifier notBlacklisted(address account) {
        require(!isBlacklisted[account], "IDRC: account is blacklisted");
        _;
    }

    constructor(address admin) {
        require(admin != address(0), "IDRC: zero admin address");
        _roles[DEFAULT_ADMIN_ROLE][admin] = true;
        _roles[MINTER_ROLE][admin] = true;
        _roles[PAUSER_ROLE][admin] = true;
        _roles[BLACKLISTER_ROLE][admin] = true;

        emit RoleGranted(DEFAULT_ADMIN_ROLE, admin, msg.sender);
        emit RoleGranted(MINTER_ROLE, admin, msg.sender);
        emit RoleGranted(PAUSER_ROLE, admin, msg.sender);
        emit RoleGranted(BLACKLISTER_ROLE, admin, msg.sender);

        uint256 chainId;
        assembly {
            chainId := chainid()
        }
        DOMAIN_SEPARATOR = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256(bytes(name)),
                keccak256(bytes("1")),
                chainId,
                address(this)
            )
        );
    }

    // --- Role Management ---
    function hasRole(bytes32 role, address account) external view returns (bool) {
        return _roles[role][account];
    }

    function grantRole(bytes32 role, address account) external onlyRole(DEFAULT_ADMIN_ROLE) {
        require(account != address(0), "IDRC: zero address");
        if (!_roles[role][account]) {
            _roles[role][account] = true;
            emit RoleGranted(role, account, msg.sender);
        }
    }

    function revokeRole(bytes32 role, address account) external onlyRole(DEFAULT_ADMIN_ROLE) {
        if (_roles[role][account]) {
            _roles[role][account] = false;
            emit RoleRevoked(role, account, msg.sender);
        }
    }

    // --- ERC-20 Functions ---
    function transfer(address to, uint256 amount)
        external
        whenNotPaused
        notBlacklisted(msg.sender)
        notBlacklisted(to)
        returns (bool)
    {
        require(to != address(0), "IDRC: transfer to zero address");
        require(balanceOf[msg.sender] >= amount, "IDRC: insufficient balance");

        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;

        emit Transfer(msg.sender, to, amount);
        return true;
    }

    function approve(address spender, uint256 amount)
        external
        whenNotPaused
        notBlacklisted(msg.sender)
        notBlacklisted(spender)
        returns (bool)
    {
        require(spender != address(0), "IDRC: approve to zero address");
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount)
        external
        whenNotPaused
        notBlacklisted(from)
        notBlacklisted(to)
        notBlacklisted(msg.sender)
        returns (bool)
    {
        require(to != address(0), "IDRC: transfer to zero address");
        require(balanceOf[from] >= amount, "IDRC: insufficient balance");

        if (allowance[from][msg.sender] != type(uint256).max) {
            require(allowance[from][msg.sender] >= amount, "IDRC: insufficient allowance");
            allowance[from][msg.sender] -= amount;
        }

        balanceOf[from] -= amount;
        balanceOf[to] += amount;

        emit Transfer(from, to, amount);
        return true;
    }

    // --- Minting & Burning ---
    function mint(address to, uint256 amount)
        external
        onlyRole(MINTER_ROLE)
        whenNotPaused
        notBlacklisted(to)
    {
        require(to != address(0), "IDRC: mint to zero address");
        require(amount > 0, "IDRC: zero amount");

        totalSupply += amount;
        balanceOf[to] += amount;

        emit Transfer(address(0), to, amount);
    }

    function burn(uint256 amount) external whenNotPaused notBlacklisted(msg.sender) {
        require(amount > 0, "IDRC: zero amount");
        require(balanceOf[msg.sender] >= amount, "IDRC: burn exceeds balance");

        balanceOf[msg.sender] -= amount;
        totalSupply -= amount;

        emit Transfer(msg.sender, address(0), amount);
    }

    // --- Pause & Blacklist ---
    function pause() external onlyRole(PAUSER_ROLE) {
        paused = true;
        emit Paused(msg.sender);
    }

    function unpause() external onlyRole(PAUSER_ROLE) {
        paused = false;
        emit Unpaused(msg.sender);
    }

    function blacklist(address account) external onlyRole(BLACKLISTER_ROLE) {
        isBlacklisted[account] = true;
        emit Blacklisted(account);
    }

    function unblacklist(address account) external onlyRole(BLACKLISTER_ROLE) {
        isBlacklisted[account] = false;
        emit Unblacklisted(account);
    }
}
