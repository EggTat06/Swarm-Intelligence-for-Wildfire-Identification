from setuptools import setup

package_name = "sim_pkg"

setup(
    name=package_name,
    version="0.0.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="user",
    maintainer_email="user@todo.todo",
    description="Swarm intelligence wildfire simulation package",
    license="TODO: License declaration",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "environment_node = sim_pkg.environment_node:main",
            "drone_node = sim_pkg.drone_node:main",
            "vision_processing = sim_pkg.vision_processing:main",
            "metrics_node = sim_pkg.metrics_node:main",
        ],
    },
)
